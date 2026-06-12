import os
import unittest
from unittest.mock import patch

from oracle_self_healing_agent.config import AgentConfig


class ConfigTests(unittest.TestCase):
    def test_oracle_thick_mode_env(self):
        config = AgentConfig()

        with patch.dict(
            os.environ,
            {
                "ORACLE_THICK_MODE": "true",
                "ORACLE_CLIENT_LIB_DIR": "/opt/oracle/instantclient",
            },
            clear=False,
        ):
            config.apply_env()

        self.assertTrue(config.database.thick_mode)
        self.assertEqual(config.database.client_lib_dir, "/opt/oracle/instantclient")


if __name__ == "__main__":
    unittest.main()
