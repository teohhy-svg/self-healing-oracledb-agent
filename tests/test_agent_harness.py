import unittest

from oracle_self_healing_agent.agent import SelfHealingAgent
from oracle_self_healing_agent.config import AgentConfig, SafetyConfig
from oracle_self_healing_agent.harness import FakeOracleClient


HEALTHY_FIXTURE = {
    "queries": {
        "tablespace_pressure": [],
        "blocking_sessions": [],
        "invalid_objects": [],
        "stale_stats": [],
        "fra_pressure": [],
    }
}


INCIDENT_FIXTURE = {
    "queries": {
        "tablespace_pressure": [
            {
                "tablespace_name": "APP_DATA",
                "used_percent": 91.0,
                "file_name": "/u02/app_data01.dbf",
                "autoextensible": "NO",
            }
        ],
        "blocking_sessions": [
            {
                "sid": 12,
                "serial_number": 1,
                "blocking_session": 99,
                "blocking_serial_number": 7,
                "seconds_in_wait": 900,
            }
        ],
        "invalid_objects": [{"owner": "APP", "object_name": "PKG_A", "object_type": "PACKAGE BODY"}],
        "stale_stats": [{"owner": "APP", "table_name": "ORDERS", "stale_stats": "YES"}],
        "fra_pressure": [{"name": "+FRA", "used_percent": 91.2, "space_reclaimable_mb": 1024}],
    }
}


class AgentHarnessTests(unittest.TestCase):
    def test_healthy_fixture_plans_no_actions(self):
        config = AgentConfig()
        client = FakeOracleClient(HEALTHY_FIXTURE)
        report = SelfHealingAgent(client, config).run_once()

        self.assertEqual(report.summary["checks_unhealthy"], 0)
        self.assertEqual(report.summary["actions_planned"], 0)

    def test_incident_fixture_is_safe_by_default(self):
        config = AgentConfig()
        client = FakeOracleClient(INCIDENT_FIXTURE)
        report = SelfHealingAgent(client, config).run_once()

        self.assertEqual(report.summary["checks_unhealthy"], 5)
        self.assertGreater(report.summary["actions_planned"], 0)
        self.assertEqual(report.summary["actions_executed"], 0)
        self.assertEqual(client.executed_sql, [])

    def test_permitted_simulated_run_executes_allowed_sql(self):
        config = AgentConfig(
            safety=SafetyConfig(
                dry_run=False,
                require_approval=False,
                allow_storage_changes=True,
                allow_session_kill=True,
                allow_stats_jobs=True,
                max_actions_per_run=10,
            )
        )
        client = FakeOracleClient(INCIDENT_FIXTURE)
        report = SelfHealingAgent(client, config).run_once()

        self.assertEqual(report.summary["actions_executed"], 4)
        self.assertEqual(len(client.executed_sql), 4)
        self.assertTrue(any("AUTOEXTEND ON" in sql for sql in client.executed_sql))
        self.assertTrue(any("KILL SESSION" in sql for sql in client.executed_sql))
        self.assertTrue(any("COMPILE_SCHEMA" in sql for sql in client.executed_sql))
        self.assertTrue(any("GATHER_SCHEMA_STATS" in sql for sql in client.executed_sql))


if __name__ == "__main__":
    unittest.main()
