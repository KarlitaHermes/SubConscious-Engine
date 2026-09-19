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
async def test_idle_skipped_when_no_target_source_session(tmp_path: Path) -> None:
    config = make_config(tmp_path, idle_enabled=True, rules=default_routing_rules())
    state = StateManager(tmp_path / "state.yaml")
    registry = AsyncMock()
    registry.find_session_for_source.return_value = None

    bus = EventBus()
    source = IdleEventSource(config, registry, state)

    with patch("src.sources.idle.get_last_human_activity", return_value=None):
        await source._evaluate(bus)

    bus.close()
    published = [e async for e in bus.consume()]
    assert published == []
    registry.find_session_for_source.assert_awaited_once_with("telegram")


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
    registry.find_session_for_source.return_value = session

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
    registry.find_session_for_source.return_value = session

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


@pytest.mark.asyncio
async def test_idle_falls_through_when_music_on_cooldown(tmp_path: Path) -> None:
    """Music preferred-window cooldown must not block other idle maintenance."""
    import time

    vault = tmp_path / "vault"
    tasks = vault / "Projects" / "Maintenance"
    tasks.mkdir(parents=True)
    (tasks / "tasks.md").write_text(
        "- [ ] Daily music curation — Last done: never\n",
        encoding="utf-8",
    )

    config = make_config(
        tmp_path,
        idle_enabled=True,
        rules=[
            {
                "event_type": "maintenance",
                "task_id": "music_curation",
                "cooldown_minutes": 1440,
                "preferred_window": {"hours": [0, 1, 2, 3, 4, 5], "max_wait_hours": 12},
                "target_sources": ["telegram"],
            },
            {
                "event_type": "maintenance",
                "cooldown_minutes": 120,
                "target_sources": ["telegram"],
            },
            {
                "event_type": "research",
                "cooldown_minutes": 120,
                "target_sources": ["telegram"],
            },
        ],
    )
    config.idle.vault_root = vault
    state = StateManager(tmp_path / "state.yaml")
    # Yesterday-morning music delivery still inside 1440m cooldown.
    state._data.setdefault("cooldowns", {})["idle_engine:music_curation"] = time.time() - 8 * 3600
    state.save()

    registry = AsyncMock()
    session = MagicMock()
    session.id = "sess_1"
    session.source = "telegram"
    registry.find_session_for_source.return_value = session

    bus = EventBus()
    source = IdleEventSource(config, registry, state)

    with patch("src.sources.idle.get_last_human_activity", return_value=None):
        await source._evaluate(bus)

    bus.close()
    published = [e async for e in bus.consume()]
    assert len(published) == 1
    assert published[0].event_type == "maintenance"
    assert published[0].task_id is None
    assert published[0].cooldown_key == "idle_engine"
    assert state.idle_trigger_count == 1


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
    registry.find_session_for_source.return_value = session

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
