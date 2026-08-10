from __future__ import annotations

from typing import Iterable, Optional

from .agentic import AgenticControlPlane
from .config import AgentConfig
from .models import HealReport
from .oracle import DatabaseClient
from .probes import DEFAULT_PROBES, Probe


class SelfHealingAgent:
    def __init__(self, client: DatabaseClient, config: AgentConfig, probes: Optional[Iterable[Probe]] = None):
        self.client = client
        self.config = config
        self.probes = list(probes or DEFAULT_PROBES)

    def run_once(self) -> HealReport:
        return AgenticControlPlane(self.client, self.config, self.probes).run_once()
