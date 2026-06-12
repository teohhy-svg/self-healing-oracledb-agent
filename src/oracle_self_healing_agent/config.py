from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DatabaseConfig:
    user: str = ""
    password: str = ""
    dsn: str = ""


@dataclass
class ThresholdConfig:
    tablespace_warning_pct: float = 85.0
    blocking_wait_seconds: int = 300
    invalid_objects_min: int = 1
    stale_stats_min: int = 1
    fra_warning_pct: float = 80.0
    datafile_autoextend_next_mb: int = 1024
    datafile_max_mb: int = 32768


@dataclass
class SafetyConfig:
    dry_run: bool = True
    require_approval: bool = True
    allow_storage_changes: bool = False
    allow_session_kill: bool = False
    allow_stats_jobs: bool = True
    max_actions_per_run: int = 5


@dataclass
class AgentConfig:
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentConfig":
        return cls(
            database=DatabaseConfig(**data.get("database", {})),
            thresholds=ThresholdConfig(**data.get("thresholds", {})),
            safety=SafetyConfig(**data.get("safety", {})),
        )

    def apply_env(self) -> None:
        self.database.user = os.getenv("ORACLE_USER", self.database.user)
        self.database.password = os.getenv("ORACLE_PASSWORD", self.database.password)
        self.database.dsn = os.getenv("ORACLE_DSN", self.database.dsn)

        dry_run = os.getenv("AGENT_DRY_RUN")
        if dry_run is not None:
            self.safety.dry_run = dry_run.strip().lower() in {"1", "true", "yes", "on"}


def load_config(path: Optional[str]) -> AgentConfig:
    if not path:
        config = AgentConfig()
        config.apply_env()
        return config

    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    config = AgentConfig.from_dict(data)
    config.apply_env()
    return config
