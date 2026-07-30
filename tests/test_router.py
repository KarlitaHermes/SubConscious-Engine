"""Tests for the event router."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.events.models import DeliveryResult, Event, EventSourceKind
from src.router.router import Router
from tests.conftest import make_config, make_session


@pytest.mark.asyncio
async def test_handle_rejects_preferred_target_with_wrong_source(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    cli_session = make_session("sess_cli_1", source="cli")
    tg_session = make_session("sess_tg_1", source="telegram")
    mock_registry.get_session.return_value = cli_session
    mock_registry.find_sessions_for_sources.return_value = [tg_session]
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_tg_1", success=True),
    ]

    config = make_config(
        tmp_path,
        rules=[{"event_type": "*", "target_sources": ["telegram"], "max_targets": 1}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="maintenance prompt",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        preferred_target="sess_cli_1",
        preferred_source="cli",
        cooldown_key="test_router_wrong_source",
    )

    results = await router.handle(event)
    assert len(results) == 1
    assert results[0].session_id == "sess_tg_1"
    mock_registry.find_sessions_for_sources.assert_awaited_once()
    call_args = mock_registry.find_sessions_for_sources.await_args
    assert call_args.args[0] == ["telegram"]


@pytest.mark.asyncio
async def test_handle_delivers_to_preferred_target(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    session = make_session("sess_tg_1")
    mock_registry.get_session.return_value = session
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_tg_1", success=True),
    ]

    config = make_config(
        tmp_path,
        rules=[{"event_type": "*", "target_sources": ["telegram"], "max_targets": 1}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="[SUBCONSCIOUS ENGINE TEST] router test",
        event_type="custom",
        source=EventSourceKind.REST,
        preferred_target="sess_tg_1",
        cooldown_key="test_router_preferred",
    )

    results = await router.handle(event)
    assert len(results) == 1
    assert results[0].success is True
    mock_registry.get_session.assert_awaited_once_with("sess_tg_1")
    mock_delivery.inject_many.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_replaces_inactive_preferred_target(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    stale = make_session("sess_old", started_at=1000.0, active=False)
    active = make_session("sess_new", started_at=500.0, active=True)
    mock_registry.get_session.return_value = stale
    mock_registry.find_session_for_source.return_value = active
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_new", success=True),
    ]

    config = make_config(
        tmp_path,
        rules=[{"event_type": "*", "target_sources": ["telegram"], "max_targets": 1}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="nudge",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        preferred_target="sess_old",
        cooldown_key="test_stale_preferred",
    )

    results = await router.handle(event)
    assert results[0].session_id == "sess_new"
    mock_registry.find_session_for_source.assert_awaited_once_with("telegram")
    mock_registry.find_sessions_for_sources.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_blocked_by_cooldown(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    config = make_config(
        tmp_path,
        rules=[{"event_type": "custom", "cooldown_minutes": 60}],
        cooldown_minutes=60,
    )
    state = _fresh_state(tmp_path)
    state.record_delivery("prev", "custom", ["s1"], success=True, cooldown_key="custom")

    router = Router(config, mock_registry, mock_delivery, state)
    event = Event(
        text="should not send",
        event_type="custom",
        source=EventSourceKind.REST,
        cooldown_key="custom",
    )

    results = await router.handle(event)
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_explicit_targets(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    s1 = make_session("sess_a")
    s2 = make_session("sess_b", started_at=999.0)
    mock_registry.get_sessions_by_ids.return_value = [s1, s2]
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_a", success=True),
        DeliveryResult(session_id="sess_b", success=True),
    ]

    config = make_config(
        tmp_path,
        rules=[{"event_type": "broadcast", "broadcast": True, "max_targets": 5}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="fan out",
        event_type="broadcast",
        source=EventSourceKind.REST,
        targets=["sess_a", "sess_b"],
        cooldown_key="test_router_broadcast",
    )

    results = await router.handle(event)
    assert len(results) == 2
    mock_registry.get_sessions_by_ids.assert_awaited_once_with(["sess_a", "sess_b"])


@pytest.mark.asyncio
async def test_handle_resolves_by_rule_sources(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    session = make_session("sess_tg_1")
    mock_registry.find_sessions_for_sources.return_value = [session]
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_tg_1", success=True),
    ]

    config = make_config(
        tmp_path,
        rules=[{"event_type": "maintenance", "target_sources": ["telegram"], "max_targets": 1}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="maintenance prompt",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        cooldown_key="test_router_maintenance",
    )

    results = await router.handle(event)
    assert len(results) == 1
    mock_registry.find_sessions_for_sources.assert_awaited_once()
    call_args = mock_registry.find_sessions_for_sources.await_args
    assert call_args.args[0] == ["telegram"]
    assert call_args.kwargs["broadcast"] is False


@pytest.mark.asyncio
async def test_handle_no_targets_returns_empty(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    mock_registry.find_sessions_for_sources.return_value = []
    config = make_config(tmp_path, rules=[{"event_type": "*", "target_sources": ["telegram"]}])
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="nowhere to go",
        event_type="custom",
        source=EventSourceKind.REST,
        cooldown_key="test_router_no_targets",
    )

    results = await router.handle(event)
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_records_failed_delivery_without_cooldown(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    session = make_session("sess_tg_1")
    mock_registry.get_session.return_value = session
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id="sess_tg_1", success=False, error="adapter error"),
    ]

    state = _fresh_state(tmp_path)
    config = make_config(tmp_path, rules=[{"event_type": "*"}])
    router = Router(config, mock_registry, mock_delivery, state)
    event = Event(
        text="fail inject",
        event_type="custom",
        source=EventSourceKind.REST,
        preferred_target="sess_tg_1",
        cooldown_key="test_router_fail",
    )

    results = await router.handle(event)
    assert results[0].success is False
    assert state.is_in_cooldown(60, key="test_router_fail") is False
    assert state.trigger_count == 0


@pytest.mark.asyncio
async def test_handle_skipped_when_no_applicable_rule(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    config = make_config(
        tmp_path,
        rules=[{"event_type": "alert", "min_event_priority": 100, "target_sources": ["telegram"]}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="low priority",
        event_type="alert",
        source=EventSourceKind.REST,
        priority=1,
        cooldown_key="test_router_priority",
    )

    results = await router.handle(event)
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_skipped_outside_active_hours(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import datetime
    from unittest.mock import MagicMock

    import src.router.rules as rules_mod

    fixed = datetime(2026, 6, 15, 3, 0)
    mock_dt = MagicMock()
    mock_dt.now.return_value = fixed
    monkeypatch.setattr(rules_mod, "datetime", mock_dt)

    config = make_config(
        tmp_path,
        rules=[{"event_type": "night_only", "target_sources": ["telegram"], "active_hours": [22, 23]}],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="wrong time",
        event_type="night_only",
        source=EventSourceKind.REST,
        cooldown_key="test_router_time",
    )

    results = await router.handle(event)
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_parks_for_preferred_window(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    from datetime import datetime

    from src.state import StateManager

    state = StateManager(tmp_path / "state.yaml")
    config = make_config(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "target_sources": ["telegram"],
                "preferred_window": {"hours": [0, 1, 2], "max_wait_hours": 12},
            },
        ],
    )
    router = Router(config, mock_registry, mock_delivery, state)
    event = Event(
        text="night maintenance",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        cooldown_key="idle_engine",
    )
    results = await router.handle(event, now=datetime(2026, 7, 30, 14, 0, 0))
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()
    parked = state.get_deferred("idle_engine")
    assert parked is not None
    assert parked["text"] == "night maintenance"
    assert parked["preferred_hours"] == [0, 1, 2]


@pytest.mark.asyncio
async def test_handle_asap_when_past_preferred_window(
    tmp_path,
    mock_registry: AsyncMock,
    mock_delivery: AsyncMock,
) -> None:
    from datetime import datetime

    tg = make_session()
    mock_registry.find_sessions_for_sources.return_value = [tg]
    mock_delivery.inject_many.return_value = [
        DeliveryResult(session_id=tg.id, success=True),
    ]
    config = make_config(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "target_sources": ["telegram"],
                "preferred_window": {"hours": [0, 1, 2], "max_wait_hours": 12},
            },
        ],
    )
    router = Router(config, mock_registry, mock_delivery, _fresh_state(tmp_path))
    event = Event(
        text="missed night — do ASAP",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        cooldown_key="idle_engine",
    )
    # 04:00 → ~20h until next window > max_wait 12 → ASAP deliver
    results = await router.handle(event, now=datetime(2026, 7, 30, 4, 0, 0))
    assert len(results) == 1
    assert results[0].success is True
    mock_delivery.inject_many.assert_awaited_once()


def _fresh_state(tmp_path):
    from src.state import StateManager

    return StateManager(tmp_path / "state.yaml")
