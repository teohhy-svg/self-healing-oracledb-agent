from __future__ import annotations

import re
from typing import Dict, Iterable, List

from .models import ActionPlan, ActionResult, CheckResult, IncidentGraph, PerformanceFinding


def build_incident_graph(
    checks: Iterable[CheckResult],
    findings: Iterable[PerformanceFinding],
    plans: Iterable[ActionPlan],
    actions: Iterable[ActionResult],
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
    check_nodes = {_check_id(check.name): check for check in checks}
    plan_nodes = {_plan_id(plan.plan_id): plan for plan in plans}

    for node_id, check in check_nodes.items():
        _add_node(graph, node_id, "check", f"{check.name}: {check.status} ({check.severity})")

    for finding in findings:
        finding_id = _finding_id(finding.finding_id)
        _add_node(graph, finding_id, "finding", f"{finding.area}: {finding.severity}")
        source = _source_check_for_finding(finding)
        if source in check_nodes:
            _add_edge(graph, source, finding_id, "produces finding")

    for node_id, plan in plan_nodes.items():
        _add_node(graph, node_id, "plan", f"{plan.action_type}: {plan.risk} risk")
        source = _check_id(plan.check_name)
        if source in check_nodes:
            _add_edge(graph, source, node_id, "triggers plan")

    for action in actions:
        action_id = _action_id(action.plan_id)
        _add_node(graph, action_id, "outcome", f"{action.status}: {action.plan_id}")
        source = _plan_id(action.plan_id)
        if source in plan_nodes:
            _add_edge(graph, source, action_id, "results in")

    return graph


def render_mermaid(graph: IncidentGraph) -> str:
    """Render the graph without a graph-library dependency or executable labels."""
    lines = ["flowchart LR"]
    for node in graph.nodes:
        node_id = _mermaid_id(node["id"])
        label = _escape_label(node["label"])
        shape = {"check": "[", "finding": "([", "plan": "{{", "outcome": "[["}.get(node["type"], "[")
        close = {"check": "]", "finding": "]) ", "plan": "}}", "outcome": "]]"}.get(node["type"], "]")
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


def _mermaid_id(value: str) -> str:
    return "n_" + re.sub(r"[^A-Za-z0-9_]", "_", value)


def _escape_label(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ")
