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


def test_allows_after_stale_in_progress_expires(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    base = 6_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("weather", 60, status="in_progress")
    gate = _gate(
        tmp_path,
        rules=[{"event_type": "*", "cooldown_minutes": 60}],
        cooldown_minutes=60,
    )
    assert gate.check(state, _event(cooldown_key="weather")) is SuppressReason.IN_PROGRESS

    t["now"] = base + 61 * 60
    assert gate.check(state, _event(cooldown_key="weather")) is None


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


def test_blocks_nudge_budget(tmp_path: Path) -> None:
    import time as _time

    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(tmp_path, rules=[{"event_type": "*"}])
    # Record 6 successful deliveries (default budget) within the last hour
    now = _time.time()
    for i in range(6):
        state.record_delivery(f"e{i}", "test", ["s1"], success=True, cooldown_key=f"k{i}")
    # The 7th event should be blocked by nudge budget
    assert gate.check(state, _event()) is SuppressReason.NUDGE_BUDGET


def test_nudge_budget_zero_means_unlimited(tmp_path: Path) -> None:
    import time as _time

    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(tmp_path, rules=[{"event_type": "*"}], nudge_budget_per_hour=0)
    for i in range(10):
        state.record_delivery(f"e{i}", "test", ["s1"], success=True, cooldown_key=f"k{i}")
    # Should still allow even after many nudges
    assert gate.check(state, _event()) is None


def test_defer_preferred_window_afternoon(tmp_path: Path) -> None:
    from datetime import datetime

    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "preferred_window": {"hours": [0, 1, 2], "max_wait_hours": 12},
            },
        ],
    )
    event = _event(event_type="maintenance", cooldown_key="idle_engine")
    reason = gate.check(state, event, now=datetime(2026, 7, 30, 14, 0, 0))
    assert reason is SuppressReason.DEFER_PREFERRED_WINDOW
    assert gate.blocks_publish(reason) is False
    assert gate.should_notify(state, event, now=datetime(2026, 7, 30, 14, 0, 0)) is True


def test_asap_when_window_too_far(tmp_path: Path) -> None:
    from datetime import datetime

    state = StateManager(tmp_path / "state.yaml")
    gate = _gate(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "preferred_window": {"hours": [0, 1, 2], "max_wait_hours": 12},
            },
        ],
    )
    event = _event(event_type="maintenance", cooldown_key="idle_engine")
    assert gate.check(state, event, now=datetime(2026, 7, 30, 4, 0, 0)) is None


def test_preferred_window_overrides_cooldown_at_midnight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Daily cooldown must not block the first nudge of a new preferred window."""
    import time as time_mod
    from datetime import datetime

    now_dt = datetime(2026, 9, 19, 0, 0, 30)
    monkeypatch.setattr(time_mod, "time", lambda: now_dt.timestamp())

    state = StateManager(tmp_path / "state.yaml")
    # Yesterday morning delivery still inside 1440m cooldown at midnight.
    state._data.setdefault("cooldowns", {})["idle_engine:music_curation"] = datetime(
        2026, 9, 18, 8, 12, 0
    ).timestamp()
    state.save()

    gate = _gate(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "task_id": "music_curation",
                "cooldown_minutes": 1440,
                "preferred_window": {
                    "hours": [0, 1, 2, 3, 4, 5],
                    "max_wait_hours": 12,
                },
            },
        ],
    )
    event = _event(
        event_type="maintenance",
        task_id="music_curation",
        cooldown_key="idle_engine:music_curation",
    )
    assert gate.check(state, event, now=now_dt) is None


def test_cooldown_still_blocks_inside_same_preferred_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cooldown still prevents fast retry within the same night window."""
    import time as time_mod
    from datetime import datetime

    now_dt = datetime(2026, 9, 19, 2, 0, 0)
    monkeypatch.setattr(time_mod, "time", lambda: now_dt.timestamp())

    state = StateManager(tmp_path / "state.yaml")
    state._data.setdefault("cooldowns", {})["idle_engine:music_curation"] = datetime(
        2026, 9, 19, 0, 15, 0
    ).timestamp()
    state.save()

    gate = _gate(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "task_id": "music_curation",
                "cooldown_minutes": 1440,
                "preferred_window": {
                    "hours": [0, 1, 2, 3, 4, 5],
                    "max_wait_hours": 12,
                },
            },
        ],
    )
    event = _event(
        event_type="maintenance",
        task_id="music_curation",
        cooldown_key="idle_engine:music_curation",
    )
    assert gate.check(state, event, now=now_dt) is SuppressReason.COOLDOWN


def test_cooldown_blocks_outside_preferred_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Outside preferred hours, cooldown behaves normally."""
    import time as time_mod
    from datetime import datetime

    now_dt = datetime(2026, 9, 18, 20, 0, 0)
    monkeypatch.setattr(time_mod, "time", lambda: now_dt.timestamp())

    state = StateManager(tmp_path / "state.yaml")
    state._data.setdefault("cooldowns", {})["idle_engine:music_curation"] = datetime(
        2026, 9, 18, 8, 12, 0
    ).timestamp()
    state.save()

    gate = _gate(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "task_id": "music_curation",
                "cooldown_minutes": 1440,
                "preferred_window": {
                    "hours": [0, 1, 2, 3, 4, 5],
                    "max_wait_hours": 12,
                },
            },
        ],
    )
    event = _event(
        event_type="maintenance",
        task_id="music_curation",
        cooldown_key="idle_engine:music_curation",
    )
    assert gate.check(state, event, now=now_dt) is SuppressReason.COOLDOWN
