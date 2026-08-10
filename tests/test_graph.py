import unittest

from oracle_self_healing_agent.agent import SelfHealingAgent
from oracle_self_healing_agent.config import AgentConfig
from oracle_self_healing_agent.graph import render_mermaid
from oracle_self_healing_agent.harness import FakeOracleClient
from test_agent_harness import INCIDENT_FIXTURE


class IncidentGraphTests(unittest.TestCase):
    def test_graph_links_evidence_to_plan_and_outcome(self):
        report = SelfHealingAgent(FakeOracleClient(INCIDENT_FIXTURE), AgentConfig()).run_once()
        edges = report.incident_graph.edges

        self.assertIn(
            {
                "source": "check:tablespace_pressure",
                "target": "plan:tablespace-autoextend-APP_DATA",
                "relationship": "triggers plan",
            },
            edges,
        )
        self.assertIn(
            {
                "source": "plan:compile-schema-APP",
                "target": "outcome:compile-schema-APP",
                "relationship": "results in",
            },
            edges,
        )
        self.assertIn("flowchart LR", render_mermaid(report.incident_graph))


if __name__ == "__main__":
    unittest.main()
