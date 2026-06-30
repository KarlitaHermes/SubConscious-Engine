"""Load config.yaml into typed Config objects."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml

from src.config.models import (
    AdapterConfig,
    Config,
    GatewayConfig,
    IdleConfig,
    LoggingConfig,
    StateConfig,
)
from src.config.parser import (
    default_routing_rules,
    expand_path,
    parse_entry_points,
    parse_routing,
)

CONFIG_ENV_VAR = "SUBCONSCIOUS_CONFIG"
DEFAULT_CONFIG_PATH = Path.home() / ".hermes" / "subconscious-engine" / "config.yaml"


def _load_api_key() -> str:
    env_path = Path.home() / ".hermes" / ".env"
    if not env_path.exists():
        return ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("API_SERVER_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def resolve_config_path(config_path: Optional[Path] = None) -> Path:
    if config_path is not None:
        return config_path
    env_path = os.getenv(CONFIG_ENV_VAR, "").strip()
    if env_path:
        return Path(os.path.expanduser(env_path))
    return DEFAULT_CONFIG_PATH


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load and validate configuration from YAML."""
    path = resolve_config_path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Config must be a YAML mapping")

    gateway_raw = raw.get("gateway", {})
    api_key = gateway_raw.get("api_key") or _load_api_key()
    gateway_url = os.getenv("GATEWAY_URL", gateway_raw.get("url", "http://127.0.0.1:8642"))
    adapter_raw = raw.get("adapter", {})
    adapter_url = os.getenv("SUBCONSCIOUS_URL", adapter_raw.get("url", "http://127.0.0.1:8769"))
    idle_raw = raw.get("idle", {})
    logging_raw = raw.get("logging", {})
    state_raw = raw.get("state", {})

    return Config(
        gateway=GatewayConfig(url=gateway_url, api_key=api_key),
        adapter=AdapterConfig(url=adapter_url),
        idle=IdleConfig(
            threshold_minutes=int(idle_raw.get("threshold_minutes", 30)),
            cooldown_minutes=int(idle_raw.get("cooldown_minutes", 60)),
            target_source=str(idle_raw.get("target_source", "telegram")),
            fallback_sources=list(idle_raw.get("fallback_sources") or []),
            vault_root=expand_path(
                idle_raw.get("vault_root", "~/Documents/Obsidian Vault"),
            ),
            wake_grace_minutes=int(idle_raw.get("wake_grace_minutes", 10)),
            nudge_budget_per_hour=int(idle_raw.get("nudge_budget_per_hour", 6)),
        ),
        logging=LoggingConfig(
            level=str(logging_raw.get("level", "INFO")),
            file=expand_path(logging_raw.get("file", "~/.hermes/logs/subconscious-engine.log")),
            max_bytes=int(logging_raw.get("max_bytes", 10_485_760)),
            backup_count=int(logging_raw.get("backup_count", 3)),
        ),
        state=StateConfig(
            file=expand_path(state_raw.get("file", "~/.hermes/subconscious-engine/state.yaml")),
        ),
        entry_points=parse_entry_points(raw),
        routing=parse_routing(raw, default_routing_rules()),
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
    )
