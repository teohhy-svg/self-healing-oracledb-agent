import unittest

from oracle_self_healing_agent.agent import SelfHealingAgent
from oracle_self_healing_agent.config import AgentConfig
from oracle_self_healing_agent.harness import FakeOracleClient
from test_agent_harness import INCIDENT_FIXTURE


class AgenticControlPlaneTests(unittest.TestCase):
    def test_specialized_agents_use_ordered_typed_handoffs(self):
        report = SelfHealingAgent(FakeOracleClient(INCIDENT_FIXTURE), AgentConfig()).run_once()

        self.assertEqual(
            [step.stage for step in report.agent_trace],
            ["observe", "analyze", "plan", "govern", "act", "verify"],
        )
        self.assertEqual(report.agent_trace[3].status, "enforced")
        self.assertIn("dry-run", report.agent_trace[3].summary)
        self.assertTrue(any(not decision.allowed for decision in report.policy_decisions))
        self.assertEqual(report.summary["actions_executed"], 0)

    def test_policy_and_executor_are_separate_roles(self):
        report = SelfHealingAgent(FakeOracleClient(INCIDENT_FIXTURE), AgentConfig()).run_once()
        roles = {step.stage: step.role for step in report.agent_trace}

        self.assertEqual(roles["govern"], "safety-governor")
        self.assertEqual(roles["act"], "bounded-executor")


if __name__ == "__main__":
    unittest.main()
