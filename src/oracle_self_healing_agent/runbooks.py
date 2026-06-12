from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List

from .config import AgentConfig
from .models import ActionPlan, CheckResult
from .oracle import first_present, sql_literal


def build_action_plan(checks: Iterable[CheckResult], config: AgentConfig) -> List[ActionPlan]:
    plans: List[ActionPlan] = []
    for check in checks:
        if check.status != "unhealthy":
            continue

        if check.name == "tablespace_pressure":
            plans.extend(_tablespace_actions(check, config))
        elif check.name == "blocking_sessions":
            plans.extend(_blocking_session_actions(check))
        elif check.name == "invalid_objects":
            plans.extend(_invalid_object_actions(check))
        elif check.name == "stale_stats":
            plans.extend(_stale_stats_actions(check, config))
        elif check.name == "fra_pressure":
            plans.extend(_fra_actions(check))

    return plans[: config.safety.max_actions_per_run]


def _tablespace_actions(check: CheckResult, config: AgentConfig) -> List[ActionPlan]:
    plans: List[ActionPlan] = []
    rows = check.evidence.get("rows", [])
    next_mb = config.thresholds.datafile_autoextend_next_mb
    max_mb = config.thresholds.datafile_max_mb

    for row in rows:
        tablespace = first_present(row, ["tablespace_name", "TABLESPACE_NAME"])
        file_name = first_present(row, ["file_name", "FILE_NAME"])
        autoextensible = str(first_present(row, ["autoextensible", "AUTOEXTENSIBLE"], "")).upper()
        used_percent = first_present(row, ["used_percent", "USED_PERCENT"], "unknown")

        if not tablespace:
            continue

        if file_name and autoextensible == "NO":
            plans.append(
                ActionPlan(
                    plan_id=f"tablespace-autoextend-{tablespace}",
                    check_name=check.name,
                    action_type="enable_datafile_autoextend",
                    reason=f"Tablespace {tablespace} is {used_percent}% used and its largest datafile is not autoextensible.",
                    risk="high",
                    kind="sql",
                    sql=(
                        "ALTER DATABASE DATAFILE "
                        f"{sql_literal(file_name)} AUTOEXTEND ON NEXT {int(next_mb)}M MAXSIZE {int(max_mb)}M"
                    ),
                    requires_approval=True,
                    capability="allow_storage_changes",
                    verification_sql=(
                        "/* verify:tablespace_pressure */ "
                        "SELECT tablespace_name, used_percent FROM dba_tablespace_usage_metrics "
                        f"WHERE tablespace_name = {sql_literal(tablespace)}"
                    ),
                    metadata={"tablespace_name": tablespace, "file_name": file_name},
                )
            )
        else:
            plans.append(
                ActionPlan(
                    plan_id=f"tablespace-advisory-{tablespace}",
                    check_name=check.name,
                    action_type="storage_advisory",
                    reason=f"Tablespace {tablespace} is {used_percent}% used; storage layout needs DBA review.",
                    risk="medium",
                    kind="manual",
                    requires_approval=True,
                    capability="allow_storage_changes",
                    metadata={"tablespace_name": tablespace, "file_name": file_name, "autoextensible": autoextensible},
                )
            )

    return plans


def _blocking_session_actions(check: CheckResult) -> List[ActionPlan]:
    plans: List[ActionPlan] = []
    seen = set()

    for row in check.evidence.get("rows", []):
        blocking_sid = first_present(row, ["blocking_session", "BLOCKING_SESSION"])
        blocking_serial = first_present(row, ["blocking_serial_number", "BLOCKING_SERIAL_NUMBER"])
        if not blocking_sid or not blocking_serial:
            continue

        session_key = f"{blocking_sid},{blocking_serial}"
        if session_key in seen:
            continue
        seen.add(session_key)

        plans.append(
            ActionPlan(
                plan_id=f"kill-blocker-{blocking_sid}-{blocking_serial}",
                check_name=check.name,
                action_type="kill_blocking_session",
                reason=f"Session {session_key} is blocking application work beyond the configured wait threshold.",
                risk="high",
                kind="sql",
                sql=f"ALTER SYSTEM KILL SESSION {sql_literal(session_key)} IMMEDIATE",
                requires_approval=True,
                capability="allow_session_kill",
                verification_sql="/* verify:blocking_sessions */ SELECT COUNT(*) AS blocking_count FROM v$session WHERE blocking_session IS NOT NULL",
                metadata={"session": session_key},
            )
        )

    return plans


def _invalid_object_actions(check: CheckResult) -> List[ActionPlan]:
    plans: List[ActionPlan] = []
    owners = check.evidence.get("owners") or _owners_from_rows(check.evidence.get("rows", []))

    for owner in owners:
        plans.append(
            ActionPlan(
                plan_id=f"compile-schema-{owner}",
                check_name=check.name,
                action_type="compile_schema",
                reason=f"Schema {owner} has invalid objects.",
                risk="low",
                kind="plsql",
                sql=f"BEGIN DBMS_UTILITY.COMPILE_SCHEMA(schema => {sql_literal(owner)}, compile_all => FALSE); END;",
                requires_approval=False,
                capability=None,
                verification_sql=(
                    "/* verify:invalid_objects */ "
                    "SELECT COUNT(*) AS invalid_count FROM dba_objects "
                    f"WHERE owner = {sql_literal(owner)} AND status = 'INVALID'"
                ),
                metadata={"owner": owner},
            )
        )

    return plans


def _stale_stats_actions(check: CheckResult, config: AgentConfig) -> List[ActionPlan]:
    if not config.safety.allow_stats_jobs:
        return [
            ActionPlan(
                plan_id="stale-stats-advisory",
                check_name=check.name,
                action_type="stats_advisory",
                reason="Stale optimizer stats were found, but automatic stats jobs are disabled.",
                risk="low",
                kind="manual",
                requires_approval=False,
                metadata={"owners": check.evidence.get("owners", [])},
            )
        ]

    plans: List[ActionPlan] = []
    owners = check.evidence.get("owners") or _owners_from_rows(check.evidence.get("rows", []))
    for owner in owners:
        plans.append(
            ActionPlan(
                plan_id=f"gather-stale-stats-{owner}",
                check_name=check.name,
                action_type="gather_stale_stats",
                reason=f"Schema {owner} has stale table optimizer statistics.",
                risk="medium",
                kind="plsql",
                sql=(
                    "BEGIN DBMS_STATS.GATHER_SCHEMA_STATS("
                    f"ownname => {sql_literal(owner)}, options => 'GATHER STALE', no_invalidate => FALSE"
                    "); END;"
                ),
                requires_approval=True,
                capability=None,
                verification_sql=(
                    "/* verify:stale_stats */ "
                    "SELECT COUNT(*) AS stale_count FROM dba_tab_statistics "
                    f"WHERE owner = {sql_literal(owner)} AND stale_stats = 'YES'"
                ),
                metadata={"owner": owner},
            )
        )

    return plans


def _fra_actions(check: CheckResult) -> List[ActionPlan]:
    rows = check.evidence.get("rows", [])
    if not rows:
        return []

    location = first_present(rows[0], ["name", "NAME"], "configured FRA")
    used_percent = first_present(rows[0], ["used_percent", "USED_PERCENT"], "unknown")
    reclaimable_mb = first_present(rows[0], ["space_reclaimable_mb", "SPACE_RECLAIMABLE_MB"], "unknown")

    return [
        ActionPlan(
            plan_id="fra-cleanup-advisory",
            check_name=check.name,
            action_type="fra_cleanup_advisory",
            reason=(
                f"FRA {location} is {used_percent}% used with approximately "
                f"{reclaimable_mb} MB reclaimable. Review RMAN retention and backups."
            ),
            risk="medium",
            kind="manual",
            requires_approval=True,
            metadata={"fra_name": location, "used_percent": used_percent, "reclaimable_mb": reclaimable_mb},
        )
    ]


def _owners_from_rows(rows: Iterable[Dict[str, object]]) -> List[str]:
    grouped = defaultdict(int)
    for row in rows:
        owner = row.get("owner") or row.get("OWNER")
        if owner:
            grouped[str(owner)] += 1
    return sorted(grouped)
