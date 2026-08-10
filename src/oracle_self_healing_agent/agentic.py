from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List

from .actions import ActionExecutor, evaluate_policy
from .config import AgentConfig
from .graph import build_incident_graph
from .models import ActionPlan, ActionResult, AgentStep, CheckResult, HealReport, PerformanceFinding, PolicyDecision
from .oracle import DatabaseClient
from .performance import PerformanceExpertEngineer
from .probes import Probe
from .runbooks import build_action_plan


@dataclass
class AgentState:
    checks: List[CheckResult] = field(default_factory=list)
    findings: List[PerformanceFinding] = field(default_factory=list)
    plans: List[ActionPlan] = field(default_factory=list)
    policy_decisions: List[PolicyDecision] = field(default_factory=list)
    actions: List[ActionResult] = field(default_factory=list)
    trace: List[AgentStep] = field(default_factory=list)


class ObservationAgent:
    role = "oracle-observer"

    def run(self, client: DatabaseClient, config: AgentConfig, probes: Iterable[Probe]) -> List[CheckResult]:
        results: List[CheckResult] = []
        for probe in probes:
            try:
                results.append(probe.run(client, config.thresholds))
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


class AnalysisAgent:
    role = "performance-analyst"

    def run(self, checks: Iterable[CheckResult], config: AgentConfig) -> List[PerformanceFinding]:
        return PerformanceExpertEngineer(config).analyze(checks)


class PlanningAgent:
    role = "remediation-planner"

    def run(self, checks: Iterable[CheckResult], config: AgentConfig) -> List[ActionPlan]:
        return build_action_plan(checks, config)


class PolicyAgent:
    role = "safety-governor"

    def run(self, config: AgentConfig, plans: Iterable[ActionPlan]) -> List[PolicyDecision]:
        decisions = []
        for plan in plans:
            reason = evaluate_policy(plan, config.safety)
            decisions.append(PolicyDecision(plan.plan_id, not bool(reason), reason or "All configured policy gates passed."))
        return decisions

    def trace(self, config: AgentConfig, decisions: Iterable[PolicyDecision]) -> AgentStep:
        decisions = list(decisions)
        gates = ["dry-run" if config.safety.dry_run else "execution-enabled"]
        if config.safety.require_approval:
            gates.append("approval-required")
        enabled = [
            name
            for name in ("allow_storage_changes", "allow_session_kill", "allow_stats_jobs")
            if bool(getattr(config.safety, name))
        ]
        allowed = sum(decision.allowed for decision in decisions)
        summary = f"{len(decisions)} plan(s) assessed; {allowed} allowed; {', '.join(gates)}; enabled capabilities: {', '.join(enabled) or 'none'}."
        return AgentStep("govern", self.role, "enforced", summary, [decision.plan_id for decision in decisions])


class RemediationAgent:
    role = "bounded-executor"

    def run(self, client: DatabaseClient, config: AgentConfig, plans: Iterable[ActionPlan]) -> List[ActionResult]:
        executor = ActionExecutor(client, config.safety)
        return [executor.execute(plan) for plan in plans]


class VerificationAgent:
    role = "outcome-verifier"

    def assess(self, actions: Iterable[ActionResult]) -> AgentStep:
        actions = list(actions)
        verified = sum(action.verification_status == "queried" for action in actions)
        failed = sum(action.status == "failed" or action.verification_status == "failed" for action in actions)
        status = "attention" if failed else "complete"
        return AgentStep(
            "verify",
            self.role,
            status,
            f"{len(actions)} outcome(s) assessed; {verified} verification query or queries completed; {failed} failure(s).",
            [action.plan_id for action in actions],
        )


class AgenticControlPlane:
    """Specialized deterministic agents with typed hand-offs and hard policy gates.

    This is agentic orchestration, not a free-form model with database access.
    An optional LLM may later advise the analyst or planner through structured
    evidence, but only the policy-governed executor can reach the database.
    """

    def __init__(self, client: DatabaseClient, config: AgentConfig, probes: Iterable[Probe]):
        self.client = client
        self.config = config
        self.probes = list(probes)

    def run_once(self) -> HealReport:
        state = AgentState()
        observer = ObservationAgent()
        state.checks = observer.run(self.client, self.config, self.probes)
        state.trace.append(
            AgentStep("observe", observer.role, "complete", f"Collected {len(state.checks)} health check result(s).", [check.name for check in state.checks])
        )

        analyst = AnalysisAgent()
        state.findings = analyst.run(state.checks, self.config)
        state.trace.append(
            AgentStep("analyze", analyst.role, "complete", f"Produced {len(state.findings)} advisory finding(s).", [finding.finding_id for finding in state.findings])
        )

        planner = PlanningAgent()
        state.plans = planner.run(state.checks, self.config)
        state.trace.append(
            AgentStep("plan", planner.role, "complete", f"Produced {len(state.plans)} bounded remediation plan(s).", [plan.plan_id for plan in state.plans])
        )

        governor = PolicyAgent()
        state.policy_decisions = governor.run(self.config, state.plans)
        state.trace.append(governor.trace(self.config, state.policy_decisions))

        executor = RemediationAgent()
        state.actions = executor.run(self.client, self.config, state.plans)
        state.trace.append(
            AgentStep("act", executor.role, "complete", f"Recorded {len(state.actions)} action outcome(s).", [action.plan_id for action in state.actions])
        )

        verifier = VerificationAgent()
        state.trace.append(verifier.assess(state.actions))

        report = HealReport(
            database=self.config.database.dsn or "harness",
            dry_run=self.config.safety.dry_run,
            checks=state.checks,
            performance_findings=state.findings,
            plans=state.plans,
            policy_decisions=state.policy_decisions,
            actions=state.actions,
            agent_trace=state.trace,
        )
        report.summary = _summarize(report)
        report.incident_graph = build_incident_graph(
            report.checks,
            report.performance_findings,
            report.plans,
            report.actions,
            report.agent_trace,
            report.policy_decisions,
        )
        return report


def _summarize(report: HealReport):
    unhealthy = [check for check in report.checks if check.status == "unhealthy"]
    errors = [check for check in report.checks if check.status == "error"]
    return {
        "checks_total": len(report.checks),
        "checks_unhealthy": len(unhealthy),
        "checks_error": len(errors),
        "performance_findings": len(report.performance_findings),
        "actions_planned": len(report.plans),
        "policy_allowed": len([decision for decision in report.policy_decisions if decision.allowed]),
        "policy_denied": len([decision for decision in report.policy_decisions if not decision.allowed]),
        "actions_executed": len([action for action in report.actions if action.status == "executed"]),
        "actions_skipped": len([action for action in report.actions if action.status == "skipped"]),
        "actions_dry_run": len([action for action in report.actions if action.status == "dry_run"]),
        "actions_manual": len([action for action in report.actions if action.status == "manual"]),
    }
