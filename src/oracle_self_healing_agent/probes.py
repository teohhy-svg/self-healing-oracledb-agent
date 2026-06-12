from __future__ import annotations

from typing import Any, Dict, List

from .config import ThresholdConfig
from .models import CheckResult
from .oracle import DatabaseClient


class Probe:
    name = "probe"
    sql = ""

    def run(self, client: DatabaseClient, thresholds: ThresholdConfig) -> CheckResult:
        rows = client.query(self.sql, self.binds(thresholds))
        return self.evaluate(rows, thresholds)

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {}

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        raise NotImplementedError


class TablespacePressureProbe(Probe):
    name = "tablespace_pressure"
    sql = """
/* probe:tablespace_pressure */
WITH ranked_files AS (
  SELECT
    tablespace_name,
    file_name,
    autoextensible,
    bytes,
    maxbytes,
    ROW_NUMBER() OVER (PARTITION BY tablespace_name ORDER BY bytes DESC) AS rn
  FROM dba_data_files
)
SELECT
  usage.tablespace_name,
  ROUND(usage.used_percent, 2) AS used_percent,
  files.file_name,
  files.autoextensible,
  ROUND(files.bytes / 1024 / 1024) AS file_mb,
  ROUND(files.maxbytes / 1024 / 1024) AS max_mb
FROM dba_tablespace_usage_metrics usage
LEFT JOIN ranked_files files
  ON files.tablespace_name = usage.tablespace_name
 AND files.rn = 1
WHERE usage.used_percent >= :warning_pct
ORDER BY usage.used_percent DESC
"""

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {"warning_pct": thresholds.tablespace_warning_pct}

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if not rows:
            return CheckResult(self.name, "ok", "info", "No tablespaces above threshold.", {"threshold_pct": thresholds.tablespace_warning_pct, "rows": []})

        top = rows[0]
        return CheckResult(
            self.name,
            "unhealthy",
            "critical" if float(top.get("used_percent", 0)) >= 95 else "warning",
            f"{len(rows)} tablespace(s) above {thresholds.tablespace_warning_pct}% usage.",
            {"threshold_pct": thresholds.tablespace_warning_pct, "rows": rows},
        )


class BlockingSessionsProbe(Probe):
    name = "blocking_sessions"
    sql = """
/* probe:blocking_sessions */
SELECT
  blocked.sid,
  blocked.serial# AS serial_number,
  blocked.username,
  blocked.blocking_session,
  blocker.serial# AS blocking_serial_number,
  blocker.username AS blocking_username,
  blocked.event,
  blocked.seconds_in_wait
FROM v$session blocked
LEFT JOIN v$session blocker
  ON blocker.sid = blocked.blocking_session
WHERE blocked.blocking_session IS NOT NULL
  AND blocked.seconds_in_wait >= :wait_seconds
ORDER BY blocked.seconds_in_wait DESC
"""

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {"wait_seconds": thresholds.blocking_wait_seconds}

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if not rows:
            return CheckResult(self.name, "ok", "info", "No long blocking sessions detected.", {"threshold_seconds": thresholds.blocking_wait_seconds, "rows": []})

        return CheckResult(
            self.name,
            "unhealthy",
            "critical",
            f"{len(rows)} blocked session(s) waiting at least {thresholds.blocking_wait_seconds} seconds.",
            {"threshold_seconds": thresholds.blocking_wait_seconds, "rows": rows},
        )


class InvalidObjectsProbe(Probe):
    name = "invalid_objects"
    sql = """
/* probe:invalid_objects */
SELECT
  owner,
  object_name,
  object_type
FROM dba_objects
WHERE status = 'INVALID'
  AND owner NOT IN ('SYS', 'SYSTEM')
ORDER BY owner, object_type, object_name
"""

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if len(rows) < thresholds.invalid_objects_min:
            return CheckResult(self.name, "ok", "info", "No invalid application objects above threshold.", {"threshold_count": thresholds.invalid_objects_min, "rows": rows})

        owners = sorted({str(row.get("owner")) for row in rows if row.get("owner")})
        return CheckResult(
            self.name,
            "unhealthy",
            "warning",
            f"{len(rows)} invalid object(s) across {len(owners)} schema(s).",
            {"threshold_count": thresholds.invalid_objects_min, "owners": owners, "rows": rows},
        )


class StaleStatsProbe(Probe):
    name = "stale_stats"
    sql = """
/* probe:stale_stats */
SELECT
  owner,
  table_name,
  stale_stats,
  TO_CHAR(last_analyzed, 'YYYY-MM-DD HH24:MI:SS') AS last_analyzed
FROM dba_tab_statistics
WHERE stale_stats = 'YES'
  AND owner NOT IN ('SYS', 'SYSTEM')
ORDER BY owner, table_name
FETCH FIRST 100 ROWS ONLY
"""

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if len(rows) < thresholds.stale_stats_min:
            return CheckResult(self.name, "ok", "info", "No stale optimizer stats above threshold.", {"threshold_count": thresholds.stale_stats_min, "rows": rows})

        owners = sorted({str(row.get("owner")) for row in rows if row.get("owner")})
        return CheckResult(
            self.name,
            "unhealthy",
            "warning",
            f"{len(rows)} stale table statistic row(s) detected.",
            {"threshold_count": thresholds.stale_stats_min, "owners": owners, "rows": rows},
        )


class FraPressureProbe(Probe):
    name = "fra_pressure"
    sql = """
/* probe:fra_pressure */
SELECT
  name,
  ROUND(space_limit / 1024 / 1024) AS space_limit_mb,
  ROUND(space_used / 1024 / 1024) AS space_used_mb,
  ROUND(space_reclaimable / 1024 / 1024) AS space_reclaimable_mb,
  ROUND((space_used / NULLIF(space_limit, 0)) * 100, 2) AS used_percent
FROM v$recovery_file_dest
WHERE (space_used / NULLIF(space_limit, 0)) * 100 >= :warning_pct
"""

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {"warning_pct": thresholds.fra_warning_pct}

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if not rows:
            return CheckResult(self.name, "ok", "info", "FRA usage below threshold.", {"threshold_pct": thresholds.fra_warning_pct, "rows": []})

        top = rows[0]
        return CheckResult(
            self.name,
            "unhealthy",
            "critical" if float(top.get("used_percent", 0)) >= 90 else "warning",
            f"Fast Recovery Area is above {thresholds.fra_warning_pct}% usage.",
            {"threshold_pct": thresholds.fra_warning_pct, "rows": rows},
        )


class ExpensiveSqlProbe(Probe):
    name = "expensive_sql"
    sql = """
/* probe:expensive_sql */
SELECT *
FROM (
  SELECT
    sql_id,
    parsing_schema_name,
    module,
    executions,
    ROUND(elapsed_time / 1000000, 2) AS elapsed_seconds,
    ROUND(cpu_time / 1000000, 2) AS cpu_seconds,
    buffer_gets,
    disk_reads,
    rows_processed,
    SUBSTR(sql_text, 1, 160) AS sql_text_sample
  FROM v$sql
  WHERE parsing_schema_name NOT IN ('SYS', 'SYSTEM')
    AND elapsed_time / 1000000 >= :elapsed_warning_seconds
  ORDER BY elapsed_time DESC
)
WHERE ROWNUM <= :top_sql_limit
"""

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {
            "elapsed_warning_seconds": thresholds.top_sql_elapsed_warning_seconds,
            "top_sql_limit": thresholds.top_sql_limit,
        }

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if not rows:
            return CheckResult(
                self.name,
                "ok",
                "info",
                "No SQL statements above the elapsed-time threshold.",
                {"threshold_seconds": thresholds.top_sql_elapsed_warning_seconds, "rows": []},
            )

        top = rows[0]
        elapsed = float(top.get("elapsed_seconds", 0))
        return CheckResult(
            self.name,
            "unhealthy",
            "critical" if elapsed >= thresholds.top_sql_elapsed_critical_seconds else "warning",
            f"{len(rows)} SQL statement(s) above {thresholds.top_sql_elapsed_warning_seconds} elapsed seconds.",
            {
                "threshold_seconds": thresholds.top_sql_elapsed_warning_seconds,
                "critical_seconds": thresholds.top_sql_elapsed_critical_seconds,
                "rows": rows,
            },
        )


class WaitClassPressureProbe(Probe):
    name = "wait_class_pressure"
    sql = """
/* probe:wait_class_pressure */
SELECT *
FROM (
  SELECT
    wait_class,
    total_waits,
    ROUND(time_waited / 100, 2) AS waited_seconds,
    ROUND(100 * time_waited / NULLIF(SUM(time_waited) OVER (), 0), 2) AS wait_pct
  FROM v$system_wait_class
  WHERE wait_class <> 'Idle'
    AND time_waited > 0
  ORDER BY wait_pct DESC
)
WHERE wait_pct >= :warning_pct
"""

    def binds(self, thresholds: ThresholdConfig) -> Dict[str, Any]:
        return {"warning_pct": thresholds.wait_class_warning_pct}

    def evaluate(self, rows: List[Dict[str, Any]], thresholds: ThresholdConfig) -> CheckResult:
        if not rows:
            return CheckResult(
                self.name,
                "ok",
                "info",
                "No dominant database wait class above threshold.",
                {"threshold_pct": thresholds.wait_class_warning_pct, "rows": []},
            )

        top = rows[0]
        wait_pct = float(top.get("wait_pct", 0))
        return CheckResult(
            self.name,
            "unhealthy",
            "critical" if wait_pct >= 65 else "warning",
            f"{len(rows)} database wait class(es) above {thresholds.wait_class_warning_pct}% of non-idle wait time.",
            {"threshold_pct": thresholds.wait_class_warning_pct, "rows": rows},
        )


DEFAULT_PROBES = [
    TablespacePressureProbe(),
    BlockingSessionsProbe(),
    InvalidObjectsProbe(),
    StaleStatsProbe(),
    FraPressureProbe(),
    ExpensiveSqlProbe(),
    WaitClassPressureProbe(),
]
