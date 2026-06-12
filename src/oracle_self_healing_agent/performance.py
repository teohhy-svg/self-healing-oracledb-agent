from __future__ import annotations

from typing import Dict, Iterable, List

from .config import AgentConfig
from .models import CheckResult, PerformanceFinding
from .oracle import first_present


class PerformanceExpertEngineer:
    def __init__(self, config: AgentConfig):
        self.config = config

    def analyze(self, checks: Iterable[CheckResult]) -> List[PerformanceFinding]:
        if not self.config.performance.enabled:
            return []

        findings: List[PerformanceFinding] = []
        for check in checks:
            if check.status != "unhealthy":
                continue

            if check.name == "expensive_sql":
                findings.extend(self._expensive_sql_findings(check))
            elif check.name == "wait_class_pressure":
                findings.extend(self._wait_class_findings(check))
            elif check.name == "stale_stats":
                findings.extend(self._stale_stats_findings(check))

        return findings[: self.config.performance.max_findings_per_run]

    def _expensive_sql_findings(self, check: CheckResult) -> List[PerformanceFinding]:
        findings: List[PerformanceFinding] = []
        for row in check.evidence.get("rows", []):
            sql_id = first_present(row, ["sql_id", "SQL_ID"], "unknown")
            schema = first_present(row, ["parsing_schema_name", "PARSING_SCHEMA_NAME"], "unknown")
            elapsed = float(first_present(row, ["elapsed_seconds", "ELAPSED_SECONDS"], 0) or 0)
            executions = int(first_present(row, ["executions", "EXECUTIONS"], 0) or 0)
            buffer_gets = int(first_present(row, ["buffer_gets", "BUFFER_GETS"], 0) or 0)
            disk_reads = int(first_present(row, ["disk_reads", "DISK_READS"], 0) or 0)
            gets_per_exec = round(buffer_gets / executions, 2) if executions else buffer_gets

            recommendation = (
                "Review the execution plan with DBMS_XPLAN or SQL Monitor, validate bind selectivity, "
                "check whether predicates have useful indexes, and compare estimated versus actual row counts. "
                "If the plan recently changed, consider SQL Plan Management before changing application SQL."
            )
            if gets_per_exec >= 100000:
                recommendation = (
                    "High logical reads per execution point to plan or access-path inefficiency. "
                    "Check join order, missing or unusable indexes, stale histograms, and row-source cardinality "
                    "before considering hints."
                )
            elif disk_reads >= 10000:
                recommendation = (
                    "High physical reads suggest heavy scan or storage pressure. Confirm the plan, segment size, "
                    "filter selectivity, and cache behavior; then decide between SQL rewrite, indexing, partition "
                    "pruning, or storage investigation."
                )

            findings.append(
                PerformanceFinding(
                    finding_id=f"perf-sql-{sql_id}",
                    severity="critical" if elapsed >= self.config.thresholds.top_sql_elapsed_critical_seconds else "warning",
                    area="sql_tuning",
                    summary=f"SQL {sql_id} in schema {schema} consumed {elapsed} elapsed seconds.",
                    recommendation=recommendation,
                    evidence={
                        "sql_id": sql_id,
                        "schema": schema,
                        "elapsed_seconds": elapsed,
                        "executions": executions,
                        "buffer_gets": buffer_gets,
                        "disk_reads": disk_reads,
                        "buffer_gets_per_execution": gets_per_exec,
                        "sql_text_sample": first_present(row, ["sql_text_sample", "SQL_TEXT_SAMPLE"], ""),
                    },
                )
            )

        return findings

    def _wait_class_findings(self, check: CheckResult) -> List[PerformanceFinding]:
        return [
            PerformanceFinding(
                finding_id=f"perf-wait-{_slug(first_present(row, ['wait_class', 'WAIT_CLASS'], 'unknown'))}",
                severity="critical" if float(first_present(row, ["wait_pct", "WAIT_PCT"], 0) or 0) >= 65 else "warning",
                area="wait_analysis",
                summary=(
                    f"{first_present(row, ['wait_class', 'WAIT_CLASS'], 'Unknown')} waits account for "
                    f"{first_present(row, ['wait_pct', 'WAIT_PCT'], 'unknown')}% of non-idle wait time."
                ),
                recommendation=self._wait_recommendation(str(first_present(row, ["wait_class", "WAIT_CLASS"], ""))),
                evidence=dict(row),
            )
            for row in check.evidence.get("rows", [])
        ]

    def _stale_stats_findings(self, check: CheckResult) -> List[PerformanceFinding]:
        owners = check.evidence.get("owners", [])
        return [
            PerformanceFinding(
                finding_id="perf-stale-stats",
                severity="warning",
                area="optimizer_statistics",
                summary=f"Stale optimizer statistics detected for schema(s): {', '.join(owners) or 'unknown'}.",
                recommendation=(
                    "Gather stale schema statistics during a controlled maintenance window, then compare execution "
                    "plans for the highest-load SQL before and after the change."
                ),
                evidence={"owners": owners, "sample_rows": check.evidence.get("rows", [])[:5]},
            )
        ]

    def _wait_recommendation(self, wait_class: str) -> str:
        recommendations: Dict[str, str] = {
            "User I/O": "Correlate top SQL with file and segment I/O. Look for full scans, missing partition pruning, slow storage, or undersized cache effects.",
            "System I/O": "Review checkpoint, DBWR, and background I/O pressure. Check storage latency and redo/archive throughput.",
            "Concurrency": "Look for hot blocks, latch contention, buffer busy waits, and high-concurrency SQL touching the same objects.",
            "Commit": "Investigate log file sync and redo write latency. Check commit frequency, redo storage, and batching opportunities.",
            "Application": "Check blocking chains, transaction scope, row lock contention, and application think time while holding locks.",
            "Network": "Review fetch size, chatty application calls, SQL*Net round trips, and client-side latency.",
            "CPU": "Rank SQL by CPU time, validate execution plans, and check whether parallelism or inefficient SQL is saturating CPU.",
        }
        return recommendations.get(
            wait_class,
            "Use AWR or ASH to identify the top SQL, sessions, modules, and objects contributing to this wait class before applying a fix.",
        )


def _slug(value: object) -> str:
    text = str(value).lower()
    slug = "".join(character if character.isalnum() else "-" for character in text)
    return "-".join(part for part in slug.split("-") if part) or "unknown"
