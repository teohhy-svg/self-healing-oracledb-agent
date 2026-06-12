from __future__ import annotations

from typing import Iterable, List, Optional

from .actions import ActionExecutor
from .config import AgentConfig
from .models import CheckResult, HealReport
from .oracle import DatabaseClient
from .performance import PerformanceExpertEngineer
from .probes import DEFAULT_PROBES, Probe
from .runbooks import build_action_plan


class SelfHealingAgent:
    def __init__(self, client: DatabaseClient, config: AgentConfig, probes: Optional[Iterable[Probe]] = None):
        self.client = client
        self.config = config
        self.probes = list(probes or DEFAULT_PROBES)

    def run_once(self) -> HealReport:
        report = HealReport(
            database=self.config.database.dsn or "harness",
            dry_run=self.config.safety.dry_run,
        )
        report.checks = self._run_probes()
        report.performance_findings = PerformanceExpertEngineer(self.config).analyze(report.checks)
        report.plans = build_action_plan(report.checks, self.config)
        executor = ActionExecutor(self.client, self.config.safety)
        report.actions = [executor.execute(plan) for plan in report.plans]
        report.summary = self._summarize(report)
        return report

    def _run_probes(self) -> List[CheckResult]:
        results: List[CheckResult] = []
        for probe in self.probes:
            try:
                results.append(probe.run(self.client, self.config.thresholds))
            except Exception as exc:
                results.append(
                    CheckResult(
                        name=probe.name,
                        status="error",
                        severity="critical",
                        summary=f"Probe failed: {exc}",
                        evidence={"error": str(exc)},
                    )
                )
        return results

    def _summarize(self, report: HealReport):
        unhealthy = [check for check in report.checks if check.status == "unhealthy"]
        errors = [check for check in report.checks if check.status == "error"]
        return {
            "checks_total": len(report.checks),
            "checks_unhealthy": len(unhealthy),
            "checks_error": len(errors),
            "performance_findings": len(report.performance_findings),
            "actions_planned": len(report.plans),
            "actions_executed": len([action for action in report.actions if action.status == "executed"]),
            "actions_skipped": len([action for action in report.actions if action.status == "skipped"]),
            "actions_dry_run": len([action for action in report.actions if action.status == "dry_run"]),
            "actions_manual": len([action for action in report.actions if action.status == "manual"]),
        }
