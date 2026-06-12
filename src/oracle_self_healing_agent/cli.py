from __future__ import annotations

import argparse
import json
import sys

from .agent import SelfHealingAgent
from .config import load_config
from .harness import run_harness
from .oracle import OracleClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-healing Oracle Database agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    harness = subparsers.add_parser("harness", help="Run against a deterministic scenario fixture.")
    harness.add_argument("--scenario", required=True, help="Path to a scenario JSON file.")
    harness.add_argument("--config", help="Path to an agent config JSON file.")
    harness.add_argument("--execute-simulated", action="store_true", help="Turn off dry-run for the fake client.")

    live = subparsers.add_parser("live", help="Run once against a live Oracle database.")
    live.add_argument("--config", help="Path to an agent config JSON file.")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(getattr(args, "config", None))

    if args.command == "harness":
        if args.execute_simulated:
            config.safety.dry_run = False
            config.safety.require_approval = False
            config.safety.allow_storage_changes = True
            config.safety.allow_session_kill = True
        report = run_harness(args.scenario, config)
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.command == "live":
        with OracleClient(config.database) as client:
            report = SelfHealingAgent(client, config).run_once()
        json.dump(report.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    parser.error("Unknown command.")
    return 2
