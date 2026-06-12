from __future__ import annotations

from typing import Dict

from .config import SafetyConfig
from .models import ActionPlan, ActionResult
from .oracle import DatabaseClient


class ActionExecutor:
    def __init__(self, client: DatabaseClient, safety: SafetyConfig):
        self.client = client
        self.safety = safety

    def execute(self, plan: ActionPlan) -> ActionResult:
        gate = self._gate(plan)
        if gate:
            return ActionResult(plan.plan_id, "skipped", gate, plan.sql)

        if plan.kind == "manual":
            return ActionResult(plan.plan_id, "manual", "Manual action recorded for DBA review.", plan.sql)

        if self.safety.dry_run:
            return ActionResult(plan.plan_id, "dry_run", "Dry-run enabled; SQL was not executed.", plan.sql)

        if not plan.sql:
            return ActionResult(plan.plan_id, "skipped", "Plan does not include executable SQL.", plan.sql)

        try:
            rowcount = self.client.execute(plan.sql)
        except Exception as exc:  # pragma: no cover - exercised by integration failures.
            return ActionResult(plan.plan_id, "failed", f"Execution failed: {exc}", plan.sql)

        result = ActionResult(plan.plan_id, "executed", f"Executed successfully; rowcount={rowcount}.", plan.sql)
        self._verify(plan, result)
        return result

    def _gate(self, plan: ActionPlan) -> str:
        if plan.capability and not bool(getattr(self.safety, plan.capability, False)):
            return f"Capability gate closed: safety.{plan.capability} is false."

        if plan.requires_approval and self.safety.require_approval:
            return "Approval gate closed: safety.require_approval is true."

        return ""

    def _verify(self, plan: ActionPlan, result: ActionResult) -> None:
        if not plan.verification_sql:
            result.verification_status = "not_configured"
            return

        try:
            rows = self.client.query(plan.verification_sql)
        except Exception as exc:  # pragma: no cover - exercised by integration failures.
            result.verification_status = "failed"
            result.verification_evidence = {"error": str(exc)}
            return

        result.verification_status = "queried"
        result.verification_evidence = _summarize_rows(rows)


def _summarize_rows(rows) -> Dict[str, object]:
    return {"row_count": len(rows), "rows": rows[:5]}
