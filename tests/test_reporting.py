import unittest

from oracle_self_healing_agent.agent import SelfHealingAgent
from oracle_self_healing_agent.config import AgentConfig
from oracle_self_healing_agent.harness import FakeOracleClient
from oracle_self_healing_agent.reporting import render_markdown_report
from test_agent_harness import INCIDENT_FIXTURE


class ReportingTests(unittest.TestCase):
    def test_markdown_report_contains_operational_sections(self):
        report = SelfHealingAgent(FakeOracleClient(INCIDENT_FIXTURE), AgentConfig()).run_once()
        markdown = render_markdown_report(report)

        self.assertIn("# Oracle Self-Healing DB Agent Report", markdown)
        self.assertIn("## Executive Summary", markdown)
        self.assertIn("## Performance Expert Findings", markdown)
        self.assertIn("## Healing Plan", markdown)
        self.assertIn("## Safety Gate Results", markdown)
        self.assertIn("## Incident Dependency Graph", markdown)
        self.assertIn("flowchart LR", markdown)
        self.assertIn("perf-sql", markdown)


if __name__ == "__main__":
    unittest.main()
