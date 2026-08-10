from __future__ import annotations

import json
from typing import Dict, Iterable, List, Optional

from .models import ActionPlan, ActionResult, CheckResult, HealReport, PerformanceFinding, PolicyDecision
from .graph import render_mermaid


def render_report(report: HealReport, output_format: str = "json") -> str:
    if output_format == "json":
        return json.dumps(report.to_dict(), indent=2)
    if output_format == "markdown":
        return render_markdown_report(report)
    if output_format == "mermaid":
        return render_mermaid(report.incident_graph)
    raise ValueError(f"Unsupported report format: {output_format}")


def render_markdown_report(report: HealReport) -> str:
    lines: List[str] = [
        "# Oracle Self-Healing DB Agent Report",
        "",
        f"Generated: `{report.started_at}`",
        f"Database: `{_text(report.database)}`",
        f"Execution mode: `{_execution_mode(report)}`",
        f"Overall status: **{_overall_status(report)}**",
        "",
        "## Executive Summary",
        "",
    ]
    lines.extend(_summary_lines(report))
    lines.extend(["", "## Agentic Execution Trace", ""])
    lines.extend(_agent_trace_table(report))
    lines.extend(["", "## Health Checks", ""])
    lines.extend(_checks_table(report.checks))
    lines.extend(["", "## Performance Expert Findings", ""])
    lines.extend(_performance_findings(report.performance_findings))
    lines.extend(["", "## Healing Plan", ""])
    lines.extend(_plans_table(report.plans))
    lines.extend(["", "## Policy Decisions", ""])
    lines.extend(_policy_table(report.policy_decisions))
    lines.extend(["", "## Safety Gate Results", ""])
    lines.extend(_actions_table(report.plans, report.actions))
    lines.extend(["", "## Incident Dependency Graph", "", "```mermaid", render_mermaid(report.incident_graph), "```"])
    lines.extend(["", "## Recommended Next Steps", ""])
    lines.extend(_next_steps(report))
    lines.append("")
    return "\n".join(lines)


def _agent_trace_table(report: HealReport) -> List[str]:
    rows = ["| Stage | Agent role | Status | Summary |", "| --- | --- | --- | --- |"]
    for step in report.agent_trace:
        rows.append(
            f"| `{_cell(step.stage)}` | `{_cell(step.role)}` | {_cell(step.status)} | {_cell(step.summary)} |"
        )
    if not report.agent_trace:
        return ["No agentic execution trace was recorded."]
    return rows


def _summary_lines(report: HealReport) -> List[str]:
    summary = report.summary
    return [
        f"- Health checks run: **{summary.get('checks_total', 0)}**",
        f"- Unhealthy checks: **{summary.get('checks_unhealthy', 0)}**",
        f"- Probe errors: **{summary.get('checks_error', 0)}**",
        f"- Performance findings: **{summary.get('performance_findings', 0)}**",
        f"- Healing actions planned: **{summary.get('actions_planned', 0)}**",
        f"- Plans allowed by policy: **{summary.get('policy_allowed', 0)}**",
        f"- Plans denied by policy: **{summary.get('policy_denied', 0)}**",
        f"- Actions executed: **{summary.get('actions_executed', 0)}**",
        f"- Actions skipped or gated: **{summary.get('actions_skipped', 0)}**",
        f"- Dry-run actions: **{summary.get('actions_dry_run', 0)}**",
        f"- Manual DBA actions: **{summary.get('actions_manual', 0)}**",
    ]


def _checks_table(checks: Iterable[CheckResult]) -> List[str]:
    rows = ["| Check | Status | Severity | Summary |", "| --- | --- | --- | --- |"]
    count = 0
    for check in checks:
        count += 1
        rows.append(
            f"| `{_cell(check.name)}` | {_cell(check.status)} | {_cell(check.severity)} | {_cell(check.summary)} |"
        )
    if count == 0:
        return ["No checks were recorded."]
    return rows


def _performance_findings(findings: Iterable[PerformanceFinding]) -> List[str]:
    rows: List[str] = []
    count = 0
    for finding in findings:
        count += 1
        rows.extend(
            [
                f"### {_title(finding.area)} - {_text(finding.severity).upper()}",
                "",
                f"**Finding ID:** `{_text(finding.finding_id)}`",
                "",
                f"**Finding:** {_text(finding.summary)}",
                "",
                f"**Recommendation:** {_text(finding.recommendation)}",
                "",
            ]
        )
        evidence = _compact_evidence(finding.evidence)
        if evidence:
            rows.extend(["**Evidence:**", "", evidence, ""])
    if count == 0:
        return ["No performance findings were detected."]
    return rows


def _plans_table(plans: Iterable[ActionPlan]) -> List[str]:
    rows = ["| Plan | Type | Risk | Approval | Reason |", "| --- | --- | --- | --- | --- |"]
    count = 0
    for plan in plans:
        count += 1
        approval = "required" if plan.requires_approval else "not required"
        rows.append(
            f"| `{_cell(plan.plan_id)}` | {_cell(plan.action_type)} | {_cell(plan.risk)} | {_cell(approval)} | {_cell(plan.reason)} |"
        )
    if count == 0:
        return ["No healing actions were planned."]
    return rows


def _actions_table(plans: Iterable[ActionPlan], actions: Iterable[ActionResult]) -> List[str]:
    plans_by_id: Dict[str, ActionPlan] = {plan.plan_id: plan for plan in plans}
    rows = ["| Action | Status | Message | SQL |", "| --- | --- | --- | --- |"]
    count = 0
    for action in actions:
        count += 1
        sql = "none"
        if action.sql:
            sql = f"`{_cell(_shorten(action.sql, 120))}`"
        plan = plans_by_id.get(action.plan_id)
        label = plan.action_type if plan else action.plan_id
        rows.append(f"| `{_cell(label)}` | {_cell(action.status)} | {_cell(action.message)} | {sql} |")
    if count == 0:
        return ["No action results were recorded."]
    return rows


def _policy_table(decisions: Iterable[PolicyDecision]) -> List[str]:
    rows = ["| Plan | Decision | Reason |", "| --- | --- | --- |"]
    count = 0
    for decision in decisions:
        count += 1
        label = "allowed" if decision.allowed else "denied"
        rows.append(f"| `{_cell(decision.plan_id)}` | {_cell(label)} | {_cell(decision.reason)} |")
    if count == 0:
        return ["No policy decisions were required."]
    return rows


def _next_steps(report: HealReport) -> List[str]:
    steps: List[str] = []
    if report.summary.get("checks_error", 0):
        steps.append("- Fix failed probes first; incomplete evidence can hide higher-priority risks.")
    if report.performance_findings:
        steps.append("- Review the performance expert findings with AWR, ASH, SQL Monitor, or DBMS_XPLAN evidence.")
    if report.summary.get("actions_skipped", 0):
        steps.append("- Review skipped actions and open safety gates only after DBA approval.")
    if report.summary.get("actions_dry_run", 0):
        steps.append("- Dry-run actions were not executed; review SQL and rerun only after approval.")
    if report.summary.get("actions_manual", 0):
        steps.append("- Manual DBA actions need operator review before remediation.")
    if not steps:
        steps.append("- No immediate remediation is required from this run.")
    if report.dry_run:
        steps.append("- Keep dry-run enabled until the action plan is reviewed in a controlled window.")
    return steps


def _overall_status(report: HealReport) -> str:
    if report.summary.get("checks_error", 0):
        return "ATTENTION REQUIRED - probe errors"
    if any(check.severity == "critical" and check.status == "unhealthy" for check in report.checks):
        return "CRITICAL"
    if report.summary.get("checks_unhealthy", 0):
        return "WARNING"
    return "HEALTHY"


def _execution_mode(report: HealReport) -> str:
    return "dry-run" if report.dry_run else "execute-enabled"


def _compact_evidence(evidence: Dict[str, object]) -> str:
    if not evidence:
        return ""
    compact = json.dumps(evidence, indent=2, default=str)
    return f"```json\n{compact}\n```"


def _title(value: str) -> str:
    return _text(value).replace("_", " ").title()


def _shorten(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


def _cell(value: Optional[object]) -> str:
    return _text(value).replace("|", "\\|").replace("\n", " ")


def _text(value: Optional[object]) -> str:
    if value is None:
        return ""
    return str(value)
