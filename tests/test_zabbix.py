import unittest

from oracle_self_healing_agent.agent import SelfHealingAgent
from oracle_self_healing_agent.config import AgentConfig, ZabbixConfig
from oracle_self_healing_agent.harness import FakeOracleClient
from oracle_self_healing_agent.zabbix import ZabbixIncidentOrchestrator, ZabbixProblem
from test_agent_harness import HEALTHY_FIXTURE, INCIDENT_FIXTURE


class FakeZabbixClient:
    def __init__(self, problems):
        self.problems = problems
        self.comments = []

    def list_open_problems(self, tags, limit):
        self.tags = tags
        self.limit = limit
        return self.problems[:limit]

    def add_comment(self, event_id, message):
        self.comments.append((event_id, message))


class ZabbixOrchestrationTests(unittest.TestCase):
    def test_disabled_integration_makes_no_zabbix_calls(self):
        zabbix = FakeZabbixClient([ZabbixProblem("100", "Oracle tablespace", "4", ["db1"], {})])
        results = ZabbixIncidentOrchestrator(zabbix, SelfHealingAgent(FakeOracleClient(HEALTHY_FIXTURE), AgentConfig()), ZabbixConfig()).run_once()

        self.assertEqual(results, [])
        self.assertFalse(hasattr(zabbix, "tags"))

    def test_gated_plan_is_published_as_review_not_resolution(self):
        zabbix = FakeZabbixClient([ZabbixProblem("100", "Oracle tablespace", "4", ["db1"], {})])
        config = ZabbixConfig(enabled=True, allow_status_updates=True)
        results = ZabbixIncidentOrchestrator(
            zabbix, SelfHealingAgent(FakeOracleClient(INCIDENT_FIXTURE), AgentConfig()), config
        ).run_once()

        self.assertEqual(results[0].status, "remediation_gated")
        self.assertTrue(results[0].published)
        self.assertEqual(zabbix.tags, {"service": "oracle"})
        self.assertIn("DBA review", zabbix.comments[0][1])


if __name__ == "__main__":
    unittest.main()
