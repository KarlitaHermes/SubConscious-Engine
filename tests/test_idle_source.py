"""Tests for idle alternation and state tracking."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.bus import EventBus
from src.events.models import EventSourceKind
from src.sources.idle import IdleEventSource
from src.state import StateManager
from src.config.parser import default_routing_rules
from tests.conftest import make_config


@pytest.mark.asyncio
async def test_idle_skipped_when_task_in_progress(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        idle_enabled=True,
        rules=default_routing_rules(),
    )
    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("idle_engine", 60, status="in_progress")
    registry = AsyncMock()
    session = MagicMock()
    session.id = "sess_1"
    session.source = "telegram"
    registry.find_best_session.return_value = session

    bus = EventBus()
    source = IdleEventSource(config, registry, state)

    with patch("src.sources.idle.get_last_human_activity", return_value=None):
        await source._evaluate(bus)

    bus.close()
    published = [e async for e in bus.consume()]
    assert published == []
    assert state.idle_trigger_count == 0


@pytest.mark.asyncio
async def test_idle_alternates_maintenance_and_research(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        idle_enabled=True,
        rules=default_routing_rules(),
    )
    state = StateManager(tmp_path / "state.yaml")
    registry = AsyncMock()
    session = MagicMock()
    session.id = "sess_1"
    session.source = "telegram"
    registry.find_best_session.return_value = session

    bus = EventBus()
    source = IdleEventSource(config, registry, state)

    with patch("src.sources.idle.get_last_human_activity", return_value=None):
        with patch.object(state, "is_in_cooldown", return_value=False):
            await source._evaluate(bus)

    published = []
    bus.close()
    async for event in bus.consume():
        published.append(event)

    assert len(published) == 1
    assert published[0].event_type == "maintenance"
    assert published[0].entry_point == "idle"
    assert state.idle_trigger_count == 1

    bus2 = EventBus()
    with patch("src.sources.idle.get_last_human_activity", return_value=None):
        with patch.object(state, "is_in_cooldown", return_value=False):
            await source._evaluate(bus2)

    bus2.close()
    async for event in bus2.consume():
        assert event.event_type == "research"
    assert state.idle_trigger_count == 2


def test_next_idle_event_type_alternation(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    assert state.next_idle_event_type() == "maintenance"
    state.record_idle_trigger()
    assert state.next_idle_event_type() == "research"
    state.record_idle_trigger()
    assert state.next_idle_event_type() == "maintenance"


@pytest.mark.asyncio
async def test_wake_emits_pending_decisions(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    reports = vault / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    (reports / "wake.md").write_text("⚠️ needs decision from Rev\n", encoding="utf-8")

    config = make_config(tmp_path, rules=default_routing_rules())
    config.idle.vault_root = vault
    state = StateManager(tmp_path / "state.yaml")
    state.set_idle_period_active(True)

    registry = AsyncMock()
    session = MagicMock()
    session.id = "sess_1"
    session.source = "telegram"
    registry.find_best_session.return_value = session

    import time

    recent = time.time() - 60

    bus = EventBus()
    source = IdleEventSource(config, registry, state)

    with patch("src.sources.idle.get_last_human_activity", return_value=recent):
        with patch.object(state, "is_in_cooldown", return_value=False):
            await source._evaluate(bus)

    events = []
    bus.close()
    async for event in bus.consume():
        events.append(event)

    types = [e.event_type for e in events]
    assert "pending_decisions" in types
    assert state.idle_period_active is False
