from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .agent import SelfHealingAgent
from .config import load_config
from .harness import evaluate_harness, run_harness
from .oracle import OracleClient
from .reporting import render_report
from .zabbix import ZabbixApiClient, ZabbixIncidentOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Self-healing Oracle Database agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    harness = subparsers.add_parser("harness", help="Run against a deterministic scenario fixture.")
    harness.add_argument("--scenario", required=True, help="Path to a scenario JSON file.")
    harness.add_argument("--config", help="Path to an agent config JSON file.")
    harness.add_argument("--execute-simulated", action="store_true", help="Turn off dry-run for the fake client.")
    harness.add_argument(
        "--assert-expectations",
        action="store_true",
        help="Fail when the scenario's optional expect contract does not match the report.",
    )
    _add_report_options(harness)

    live = subparsers.add_parser("live", help="Run once against a live Oracle database.")
    live.add_argument("--config", help="Path to an agent config JSON file.")
    _add_report_options(live)

    zabbix = subparsers.add_parser("zabbix", help="Process tagged open Zabbix problems through the Oracle control loop.")
    zabbix.add_argument("--config", required=True, help="Path to an agent config JSON file with zabbix.enabled=true.")

    return parser


def _add_report_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--output-format",
        choices=["json", "markdown", "mermaid"],
        default="json",
        help="Report format to print to stdout.",
    )
    parser.add_argument(
        "--report-file",
        help="Optional path to save a report. The file extension .md uses Markdown; all other extensions use the selected output format.",
    )


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
        if args.assert_expectations:
            report, mismatches = evaluate_harness(args.scenario, config)
            if mismatches:
                parser.error("Harness expectation failure: " + "; ".join(mismatches))
        else:
            report = run_harness(args.scenario, config)
        _emit_report(report, args)
        return 0

    if args.command == "live":
        with OracleClient(config.database) as client:
            report = SelfHealingAgent(client, config).run_once()
        _emit_report(report, args)
        return 0

    if args.command == "zabbix":
        if not config.zabbix.enabled:
            parser.error("Zabbix integration is disabled. Set zabbix.enabled=true in the config.")
        with OracleClient(config.database) as database_client:
            agent = SelfHealingAgent(database_client, config)
            results = ZabbixIncidentOrchestrator(ZabbixApiClient(config.zabbix), agent, config.zabbix).run_once()
        sys.stdout.write(json.dumps({"results": [asdict(result) for result in results]}, indent=2))
        sys.stdout.write("\n")
        return 0

    parser.error("Unknown command.")
    return 2


def _emit_report(report, args) -> None:
    output = render_report(report, args.output_format)
    sys.stdout.write(output)
    sys.stdout.write("\n")

    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        file_format = "markdown" if report_path.suffix.lower() == ".md" else args.output_format
        report_path.write_text(render_report(report, file_format) + "\n", encoding="utf-8")
