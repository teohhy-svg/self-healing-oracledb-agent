from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class CheckResult:
    name: str
    status: str
    severity: str
    summary: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionPlan:
    plan_id: str
    check_name: str
    action_type: str
    reason: str
    risk: str
    kind: str
    sql: Optional[str] = None
    requires_approval: bool = True
    capability: Optional[str] = None
    verification_sql: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    plan_id: str
    allowed: bool
    reason: str


@dataclass
class ActionResult:
    plan_id: str
    status: str
    message: str
    sql: Optional[str] = None
    verification_status: str = "not_run"
    verification_evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceFinding:
    finding_id: str
    severity: str
    area: str
    summary: str
    recommendation: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class IncidentGraph:
    """A small, dependency-free representation of an incident control graph."""

    nodes: List[Dict[str, str]] = field(default_factory=list)
    edges: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class AgentStep:
    """An auditable hand-off in the agentic control plane."""

    stage: str
    role: str
    status: str
    summary: str
    artifact_ids: List[str] = field(default_factory=list)


@dataclass
class HealReport:
    database: str
    dry_run: bool
    started_at: str = field(default_factory=utc_now_iso)
    checks: List[CheckResult] = field(default_factory=list)
    performance_findings: List[PerformanceFinding] = field(default_factory=list)
    plans: List[ActionPlan] = field(default_factory=list)
    policy_decisions: List[PolicyDecision] = field(default_factory=list)
    actions: List[ActionResult] = field(default_factory=list)
    agent_trace: List[AgentStep] = field(default_factory=list)
    incident_graph: IncidentGraph = field(default_factory=IncidentGraph)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
