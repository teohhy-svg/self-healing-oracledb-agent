from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .agent import SelfHealingAgent
from .config import ZabbixConfig
from .models import HealReport


@dataclass
class ZabbixProblem:
    event_id: str
    name: str
    severity: str
    hosts: List[str]
    tags: Dict[str, str]


@dataclass
class ZabbixAutomationResult:
    event_id: str
    status: str
    message: str
    report: HealReport
    published: bool = False


class ZabbixIncidentClient(Protocol):
    def list_open_problems(self, tags: Dict[str, str], limit: int) -> List[ZabbixProblem]:
        ...

    def add_comment(self, event_id: str, message: str) -> None:
        ...


class ZabbixApiClient:
    """Minimal Zabbix JSON-RPC adapter; credentials stay in environment/config only."""

    def __init__(self, config: ZabbixConfig):
        if not config.url or not config.api_token:
            raise RuntimeError("Zabbix integration requires ZABBIX_URL and ZABBIX_API_TOKEN.")
        self.url = config.url.rstrip("/") + "/api_jsonrpc.php"
        self.api_token = config.api_token
        self._request_id = 0

    def list_open_problems(self, tags: Dict[str, str], limit: int) -> List[ZabbixProblem]:
        result = self._call(
            "problem.get",
            {
                "output": ["eventid", "name", "severity"],
                "selectHosts": ["host"],
                "selectTags": "extend",
                "tags": [{"tag": key, "value": value} for key, value in sorted(tags.items())],
                "sortfield": ["eventid"],
                "sortorder": "DESC",
                "limit": limit,
            },
        )
        return [
            ZabbixProblem(
                event_id=str(row["eventid"]),
                name=str(row.get("name", "unnamed problem")),
                severity=str(row.get("severity", "unknown")),
                hosts=[str(host.get("host", "unknown")) for host in row.get("hosts", [])],
                tags={str(tag.get("tag")): str(tag.get("value", "")) for tag in row.get("tags", [])},
            )
            for row in result
        ]

    def add_comment(self, event_id: str, message: str) -> None:
        # 2 = acknowledge and 4 = add message. Closing is deliberately absent.
        self._call("event.acknowledge", {"eventids": [event_id], "action": 6, "message": message})

    def _call(self, method: str, params: Dict[str, Any]) -> Any:
        self._request_id += 1
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": self._request_id}).encode()
        request = Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json-rpc", "Authorization": f"Bearer {self.api_token}"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15) as response:
                body = json.load(response)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError(f"Zabbix API request failed: {exc}") from exc
        if "error" in body:
            error = body["error"]
            raise RuntimeError(f"Zabbix API error {error.get('code')}: {error.get('data', error.get('message'))}")
        return body.get("result", [])


class ZabbixIncidentOrchestrator:
    """Correlate tagged Zabbix problems to one safe Oracle control-loop run.

    A comment can be published only by an explicit status-update flag. Problem
    closure is never automatic: an executed SQL statement and a query are not
    proof that the trigger has recovered.
    """

    def __init__(self, client: ZabbixIncidentClient, agent: SelfHealingAgent, config: ZabbixConfig):
        self.client = client
        self.agent = agent
        self.config = config

    def run_once(self) -> List[ZabbixAutomationResult]:
        if not self.config.enabled:
            return []
        results = []
        for problem in self.client.list_open_problems(self.config.problem_tags, self.config.max_problems_per_run):
            report = self.agent.run_once()
            status, message = _resolution_status(problem, report)
            published = False
            if self.config.allow_status_updates:
                self.client.add_comment(problem.event_id, message)
                published = True
            results.append(ZabbixAutomationResult(problem.event_id, status, message, report, published))
        return results


def _resolution_status(problem: ZabbixProblem, report: HealReport) -> tuple[str, str]:
    summary = report.summary
    prefix = f"Oracle healing agent run for Zabbix problem {problem.event_id}:"
    if summary.get("checks_error", 0):
        return "evidence_incomplete", f"{prefix} probe errors detected; no resolution claim was made."
    if summary.get("actions_executed", 0):
        return "remediation_pending_trigger_recovery", (
            f"{prefix} remediation executed; wait for the Zabbix trigger recovery and DBA verification before closure."
        )
    if summary.get("actions_planned", 0):
        return "remediation_gated", f"{prefix} remediation was planned but gated or dry-run; DBA review is required."
    return "no_remediation_needed", f"{prefix} no automated remediation was indicated by the current Oracle checks."
