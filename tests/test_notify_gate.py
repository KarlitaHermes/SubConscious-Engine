"""Tests for the shared notify gate."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.events.models import Event, EventSourceKind
from src.notify_gate import NotifyGate, SuppressReason
from src.state import StateManager
from tests.conftest import make_config


def _gate(tmp_path: Path, **kwargs) -> NotifyGate:
    return NotifyGate(make_config(tmp_path, **kwargs))


def _event(**kwargs) -> Event:
    defaults = {
        "text": "test",
        "event_type": "custom",
        "source": EventSourceKind.REST,
        "entry_point": "api",
    }
    defaults.update(kwargs)
    return Event(**defaults)


def test_allows_when_no_blocks(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(tmp_path, rules=[{"event_type": "*", "target_sources": ["telegram"]}])
    assert gate.should_notify(state, _event()) is True


def test_blocks_no_rule(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(
        tmp_path,
        rules=[{"event_type": "maintenance", "target_sources": ["telegram"]}],
    )
    reason = gate.check(state, _event(event_type="custom"))
    assert reason is SuppressReason.NO_RULE


def test_blocks_cooldown(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e1", "custom", ["s1"], success=True, cooldown_key="custom")
    gate = _gate(tmp_path, rules=[{"event_type": "*", "cooldown_minutes": 60}])
    assert gate.check(state, _event(cooldown_key="custom")) is SuppressReason.COOLDOWN


def test_blocks_in_progress(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("weather", 60, status="in_progress")
    gate = _gate(tmp_path, rules=[{"event_type": "*"}])
    assert gate.check(state, _event(cooldown_key="weather")) is SuppressReason.IN_PROGRESS


def test_blocks_poll_seen(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.mark_poll_item_seen("weather_poll", "alert-1")
    gate = _gate(tmp_path, rules=[{"event_type": "*"}])
    event = _event(entry_point="weather_poll", source=EventSourceKind.HTTP_POLL)
    assert (
        gate.check(state, event, poll_item_key="alert-1") is SuppressReason.POLL_SEEN
    )


def test_any_actionable_poll_items(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.mark_poll_item_seen("poll", "seen-1")
    gate = _gate(tmp_path, rules=[{"event_type": "*"}])
    items = [
        (
            Event(
                text="old",
                event_type="custom",
                source=EventSourceKind.HTTP_POLL,
                entry_point="poll",
            ),
            "seen-1",
        ),
        (
            Event(
                text="new",
                event_type="custom",
                source=EventSourceKind.HTTP_POLL,
                entry_point="poll",
                cooldown_key="fresh",
            ),
            "new-1",
        ),
    ]
    assert gate.any_actionable_poll_items(state, "poll", items) is True


def test_should_fetch_poll_skips_text_format_in_cooldown(tmp_path: Path) -> None:
    from src.config.models import EntryPoint, HandleConfig

    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e1", "weather", ["s1"], success=True, cooldown_key="weather")
    gate = _gate(tmp_path, rules=[{"event_type": "weather", "cooldown_minutes": 60}])
    entry_point = EntryPoint(
        id="wx",
        type="http_poll",
        url="http://example.com",
        handle=HandleConfig(
            default_event_type="weather",
            response_format="text",
        ),
    )
    assert gate.should_fetch_poll(state, entry_point) is False


def test_should_fetch_poll_always_fetches_open_meteo(tmp_path: Path) -> None:
    from src.config.models import EntryPoint, HandleConfig

    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e1", "weather", ["s1"], success=True, cooldown_key="weather")
    gate = _gate(tmp_path, rules=[{"event_type": "weather", "cooldown_minutes": 60}])
    entry_point = EntryPoint(
        id="wx",
        type="http_poll",
        url="http://example.com",
        handle=HandleConfig(
            default_event_type="weather",
            response_format="open_meteo",
        ),
    )
    assert gate.should_fetch_poll(state, entry_point) is True
