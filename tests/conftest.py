"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.config import (
    AdapterConfig,
    Config,
    EntryPoint,
    GatewayConfig,
    HandleConfig,
    IdleConfig,
    LoggingConfig,
    RoutingConfig,
    StateConfig,
)
from src.delivery.sessions import SessionInfo


def make_config(
    tmp_path: Path,
    rules: list[dict[str, Any]] | None = None,
    cooldown_minutes: int = 60,
    *,
    idle_enabled: bool = False,
    nudge_budget_per_hour: int = 6,
) -> Config:
    """Build a minimal Config for tests."""
    return Config(
        gateway=GatewayConfig(url="http://127.0.0.1:8642", api_key="test-key"),
        adapter=AdapterConfig(url="http://127.0.0.1:8769"),
        idle=IdleConfig(
            threshold_minutes=30,
            cooldown_minutes=cooldown_minutes,
            target_source="telegram",
            fallback_sources=["cli"],
            vault_root=tmp_path / "vault",
            wake_grace_minutes=10,
            nudge_budget_per_hour=nudge_budget_per_hour,
        ),
        logging=LoggingConfig(
            level="INFO",
            file=tmp_path / "test.log",
            max_bytes=1024,
            backup_count=1,
        ),
        state=StateConfig(file=tmp_path / "state.yaml"),
        entry_points=[
            EntryPoint(
                id="events_drop",
                type="directory",
                enabled=True,
                path=tmp_path / "events",
                poll_interval_seconds=1,
                handle=HandleConfig(default_event_type="custom"),
            ),
            EntryPoint(
                id="api",
                type="http",
                enabled=False,
                host="127.0.0.1",
                port=8770,
                handle=HandleConfig(default_event_type="custom"),
            ),
            EntryPoint(id="idle", type="idle", enabled=idle_enabled),
        ],
        routing=RoutingConfig(rules=rules or []),
        poll_interval_seconds=60,
    )


def make_session(
    session_id: str = "sess_telegram_1",
    source: str = "telegram",
    started_at: float = 1000.0,
) -> SessionInfo:
    return SessionInfo(
        id=session_id,
        source=source,
        user_id="user1",
        title="Test Session",
        started_at=started_at,
        message_count=5,
    )


@pytest.fixture
def mock_registry() -> AsyncMock:
    registry = AsyncMock()
    registry.get_session.return_value = None
    registry.get_sessions_by_ids.return_value = []
    registry.find_sessions_for_sources.return_value = []
    registry.find_best_session.return_value = None
    registry.list_sessions.return_value = []
    return registry


@pytest.fixture
def mock_delivery() -> AsyncMock:
    delivery = AsyncMock()
    delivery.inject_many.return_value = []
    delivery.inject_prompt.return_value = None
    return delivery
