from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .agent import SelfHealingAgent
from .config import AgentConfig
from .models import HealReport


PROBE_RE = re.compile(r"/\*\s*(?:probe|verify):([a-zA-Z0-9_]+)\s*\*/")


class FakeOracleClient:
    def __init__(self, fixture: Dict[str, Any]):
        self.fixture = fixture
        self.executed_sql: List[str] = []

    @classmethod
    def from_path(cls, path: str) -> "FakeOracleClient":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def query(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        key = self._key(sql)
        queries = self.fixture.get("queries", {})
        if key not in queries:
            raise KeyError(f"Fixture does not define query result for '{key}'.")
        rows = queries[key]
        return [dict(row) for row in rows]

    def execute(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> int:
        failures = self.fixture.get("execution_failures", [])
        for pattern in failures:
            if pattern in sql:
                raise RuntimeError(f"Simulated execution failure for pattern: {pattern}")

        self.executed_sql.append(sql)
        return 1

    def _key(self, sql: str) -> str:
        match = PROBE_RE.search(sql)
        if not match:
            raise KeyError("SQL does not include a /* probe:name */ or /* verify:name */ fixture marker.")
        return match.group(1)


def run_harness(scenario_path: str, config: AgentConfig):
    client = FakeOracleClient.from_path(scenario_path)
    agent = SelfHealingAgent(client, config)
    return agent.run_once()


def evaluate_harness(scenario_path: str, config: AgentConfig) -> tuple[HealReport, List[str]]:
    """Run a fixture and check the explicit regression contract in ``expect``.

    Expectations are deliberately narrow: they make safety and planning
    regressions visible without baking implementation details into fixtures.
    """
    client = FakeOracleClient.from_path(scenario_path)
    report = SelfHealingAgent(client, config).run_once()
    expected = client.fixture.get("expect", {})
    mismatches: List[str] = []

    for name, value in expected.get("summary", {}).items():
        actual = report.summary.get(name)
        if actual != value:
            mismatches.append(f"summary.{name}: expected {value!r}, got {actual!r}")

    if "action_statuses" in expected:
        actual_statuses = [action.status for action in report.actions]
        if actual_statuses != expected["action_statuses"]:
            mismatches.append(
                f"action_statuses: expected {expected['action_statuses']!r}, got {actual_statuses!r}"
            )

    return report, mismatches
