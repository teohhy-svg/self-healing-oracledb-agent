from __future__ import annotations

import re
from typing import Dict, Iterable, List

from .models import ActionPlan, ActionResult, AgentStep, CheckResult, IncidentGraph, PerformanceFinding, PolicyDecision


def build_incident_graph(
    checks: Iterable[CheckResult],
    findings: Iterable[PerformanceFinding],
    plans: Iterable[ActionPlan],
    actions: Iterable[ActionResult],
    agent_steps: Iterable[AgentStep] = (),
    policy_decisions: Iterable[PolicyDecision] = (),
) -> IncidentGraph:
    """Connect operational evidence to the decisions and outcomes it caused.

    The graph intentionally records causality, not an inferred root cause. A
    check can *trigger* a plan without proving that it caused the underlying
    database incident.
    """
    graph = IncidentGraph()
    checks = list(checks)
    findings = list(findings)
    plans = list(plans)
    actions = list(actions)
    agent_steps = list(agent_steps)
    policy_decisions = list(policy_decisions)
    check_nodes = {_check_id(check.name): check for check in checks}
    plan_nodes = {_plan_id(plan.plan_id): plan for plan in plans}

    previous_agent_id = ""
    for step in agent_steps:
        agent_id = _agent_id(step.stage)
        _add_node(graph, agent_id, "agent", f"{step.role}: {step.status}")
        if previous_agent_id:
            _add_edge(graph, previous_agent_id, agent_id, "hands off")
        previous_agent_id = agent_id

    for node_id, check in check_nodes.items():
        _add_node(graph, node_id, "check", f"{check.name}: {check.status} ({check.severity})")
        if agent_steps:
            _add_edge(graph, _agent_id("observe"), node_id, "emits evidence")

    for finding in findings:
        finding_id = _finding_id(finding.finding_id)
        _add_node(graph, finding_id, "finding", f"{finding.area}: {finding.severity}")
        source = _source_check_for_finding(finding)
        if source in check_nodes:
            _add_edge(graph, source, finding_id, "produces finding")
        if agent_steps:
            _add_edge(graph, _agent_id("analyze"), finding_id, "emits advice")

    for node_id, plan in plan_nodes.items():
        _add_node(graph, node_id, "plan", f"{plan.action_type}: {plan.risk} risk")
        source = _check_id(plan.check_name)
        if source in check_nodes:
            _add_edge(graph, source, node_id, "triggers plan")
        if agent_steps:
            _add_edge(graph, _agent_id("plan"), node_id, "proposes")

    for decision in policy_decisions:
        decision_id = _policy_id(decision.plan_id)
        label = "allowed" if decision.allowed else "denied"
        _add_node(graph, decision_id, "policy", f"policy: {label}")
        _add_edge(graph, _plan_id(decision.plan_id), decision_id, "policy input")
        _add_edge(graph, _agent_id("govern"), decision_id, "decides")

    for action in actions:
        action_id = _action_id(action.plan_id)
        _add_node(graph, action_id, "outcome", f"{action.status}: {action.plan_id}")
        source = _plan_id(action.plan_id)
        if source in plan_nodes:
            _add_edge(graph, source, action_id, "results in")
        if agent_steps:
            _add_edge(graph, _agent_id("act"), action_id, "records outcome")
            _add_edge(graph, action_id, _agent_id("verify"), "verification input")
        if policy_decisions:
            _add_edge(graph, _policy_id(action.plan_id), action_id, "constrains")

    return graph


def render_mermaid(graph: IncidentGraph) -> str:
    """Render the graph without a graph-library dependency or executable labels."""
    lines = ["flowchart LR"]
    for node in graph.nodes:
        node_id = _mermaid_id(node["id"])
        label = _escape_label(node["label"])
        shape = {"agent": "([", "check": "[", "finding": "([", "plan": "{{", "policy": "{", "outcome": "[["}.get(node["type"], "[")
        close = {"agent": "])", "check": "]", "finding": "])", "plan": "}}", "policy": "}", "outcome": "]]"}.get(node["type"], "]")
        lines.append(f'  {node_id}{shape}"{label}"{close}'.rstrip())
    for edge in graph.edges:
        lines.append(
            f'  {_mermaid_id(edge["source"])} -->|"{_escape_label(edge["relationship"])}"| {_mermaid_id(edge["target"])}'
        )
    return "\n".join(lines)


def _source_check_for_finding(finding: PerformanceFinding) -> str:
    by_area = {
        "sql_tuning": "expensive_sql",
        "wait_analysis": "wait_class_pressure",
        "optimizer_statistics": "stale_stats",
    }
    return _check_id(by_area.get(finding.area, ""))


def _add_node(graph: IncidentGraph, node_id: str, node_type: str, label: str) -> None:
    graph.nodes.append({"id": node_id, "type": node_type, "label": label})


def _add_edge(graph: IncidentGraph, source: str, target: str, relationship: str) -> None:
    graph.edges.append({"source": source, "target": target, "relationship": relationship})


def _check_id(value: str) -> str:
    return f"check:{value}"


def _finding_id(value: str) -> str:
    return f"finding:{value}"


def _plan_id(value: str) -> str:
    return f"plan:{value}"


def _action_id(value: str) -> str:
    return f"outcome:{value}"


def _agent_id(value: str) -> str:
    return f"agent:{value}"


def _policy_id(value: str) -> str:
    return f"policy:{value}"


def _mermaid_id(value: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", value)


def _escape_label(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ")
