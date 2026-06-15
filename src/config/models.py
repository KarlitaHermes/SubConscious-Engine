"""Configuration dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class GatewayConfig:
    url: str
    api_key: str


@dataclass
class AdapterConfig:
    url: str


@dataclass
class IdleConfig:
    threshold_minutes: int
    cooldown_minutes: int
    target_source: str
    fallback_sources: list[str]
    vault_root: Path
    wake_grace_minutes: int = 10


@dataclass
class LoggingConfig:
    level: str
    file: Path
    max_bytes: int
    backup_count: int


@dataclass
class StateConfig:
    file: Path


@dataclass
class HandleConfig:
    """How to interpret events from an entry point."""

    parser: str = "auto"
    handler: str = "event_file"
    default_event_type: str = "custom"
    default_priority: int = 0


@dataclass
class EntryPoint:
    """Declarative event ingress — directory, http, or idle."""

    id: str
    type: str
    enabled: bool = True
    path: Optional[Path] = None
    poll_interval_seconds: float = 5.0
    archive_dir: Optional[Path] = None
    host: str = "127.0.0.1"
    port: int = 8770
    api_key: str = ""
    handle: HandleConfig = field(default_factory=HandleConfig)


@dataclass
class RoutingConfig:
    rules: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Config:
    gateway: GatewayConfig
    adapter: AdapterConfig
    idle: IdleConfig
    logging: LoggingConfig
    state: StateConfig
    entry_points: list[EntryPoint]
    routing: RoutingConfig
    poll_interval_seconds: int = 60

    @property
    def router(self) -> RoutingConfig:
        """Backward-compatible alias."""
        return self.routing
