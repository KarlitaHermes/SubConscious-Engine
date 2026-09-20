"""Tests for state management and cooldown logic."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml

from src.state import StateManager


def test_is_in_cooldown_false_when_never_triggered(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    assert state.is_in_cooldown(60, key="maintenance") is False


def test_is_in_cooldown_true_after_record(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery(
        event_id="e1",
        event_type="test",
        session_ids=["sess1"],
        success=True,
        cooldown_key="maintenance",
    )
    assert state.is_in_cooldown(60, key="maintenance") is True


def test_is_in_cooldown_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = StateManager(tmp_path / "state.yaml")
    base = 1_000_000.0
    monkeypatch.setattr(time, "time", lambda: base)
    state.record_delivery(
        event_id="e1",
        event_type="test",
        session_ids=["sess1"],
        success=True,
        cooldown_key="maintenance",
    )
    monkeypatch.setattr(time, "time", lambda: base + 61 * 60)
    assert state.is_in_cooldown(60, key="maintenance") is False


def test_record_delivery_failed_does_not_set_cooldown(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery(
        event_id="e1",
        event_type="test",
        session_ids=[],
        success=False,
        cooldown_key="maintenance",
    )
    assert state.is_in_cooldown(60, key="maintenance") is False
    assert state.trigger_count == 0


def test_record_delivery_increments_trigger_count(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e1", "test", ["s1"], success=True)
    state.record_delivery("e2", "test", ["s1"], success=True)
    assert state.trigger_count == 2


def test_load_existing_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = 3_000_000.0
    monkeypatch.setattr(time, "time", lambda: now)
    state_file = tmp_path / "state.yaml"
    state_file.write_text(
        yaml.safe_dump({"trigger_count": 7, "cooldowns": {"idle": now - 30}}),
        encoding="utf-8",
    )
    state = StateManager(state_file)
    assert state.trigger_count == 7
    assert state.is_in_cooldown(60, key="idle") is True


def test_load_corrupt_state_uses_defaults(tmp_path: Path) -> None:
    state_file = tmp_path / "state.yaml"
    state_file.write_text(":::not yaml:::", encoding="utf-8")
    state = StateManager(state_file)
    assert state.trigger_count == 0


def test_save_persists_to_disk(tmp_path: Path) -> None:
    state_file = tmp_path / "state.yaml"
    state = StateManager(state_file)
    state.record_delivery("e1", "test", ["s1"], success=True, cooldown_key="k1")
    reloaded = StateManager(state_file)
    assert reloaded.trigger_count == 1
    assert reloaded.is_in_cooldown(60, key="k1") is True


def test_delivery_history_capped_at_100(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state = StateManager(tmp_path / "state.yaml")
    base = 2_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    for i in range(105):
        t["now"] = base + i
        state.record_delivery(f"e{i}", "test", ["s1"], success=True)

    raw = yaml.safe_load((tmp_path / "state.yaml").read_text(encoding="utf-8"))
    assert len(raw["deliveries"]) == 100
    assert raw["deliveries"][0]["event_id"] == "e5"


def test_poll_item_seen_tracking(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    assert state.is_poll_item_seen("feed", "item-1") is False
    state.mark_poll_item_seen("feed", "item-1")
    assert state.is_poll_item_seen("feed", "item-1") is True
    reloaded = StateManager(tmp_path / "state.yaml")
    assert reloaded.is_poll_item_seen("feed", "item-1") is True


def test_record_ack_sets_cooldown_and_agent_handled(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.set_idle_period_active(True)
    state.record_ack("idle_engine", 60, status="done", reset_idle_period=True, event_id="evt1")
    assert state.is_in_cooldown(60, key="idle_engine") is True
    assert state.last_agent_handled is not None
    assert state.idle_period_active is False
    assert state.is_task_in_progress("idle_engine") is False


def test_record_ack_in_progress_counts_as_activity(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("idle_engine", 60, status="in_progress", event_id="evt1")
    assert state.is_task_in_progress("idle_engine") is True
    assert state.last_agent_handled is not None
    assert state.is_in_cooldown(60, key="idle_engine") is False

    state.record_ack("idle_engine", 60, status="done")
    assert state.is_task_in_progress("idle_engine") is False
    assert state.is_in_cooldown(60, key="idle_engine") is True


def test_in_progress_expires_after_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = 5_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("idle_engine", 60, status="in_progress")
    assert state.is_task_in_progress("idle_engine", timeout_minutes=60) is True

    t["now"] = base + 61 * 60
    assert state.is_task_in_progress("idle_engine", timeout_minutes=60) is False
    assert state.is_task_in_progress("idle_engine") is False


def test_note_active_session_clears_in_progress_on_change(tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("idle_engine", 60, status="in_progress")
    state.note_active_session("telegram", "sess_old")
    assert state.is_task_in_progress("idle_engine") is True

    changed = state.note_active_session("telegram", "sess_new")
    assert changed is True
    assert state.is_task_in_progress("idle_engine") is False

    # Same id is a no-op
    state.record_ack("idle_engine", 60, status="in_progress")
    assert state.note_active_session("telegram", "sess_new") is False
    assert state.is_task_in_progress("idle_engine") is True


def test_nudge_budget_window_counts_recent_deliveries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    state = StateManager(tmp_path / "state.yaml")
    assert state.nudge_count_window(3600) == 0

    # Record 3 successful deliveries
    for i in range(3):
        t["now"] = base + i * 60
        state.record_delivery(f"e{i}", "test", ["s1"], success=True)

    assert state.nudge_count_window(3600) == 3


def test_nudge_budget_window_excludes_old_deliveries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    state = StateManager(tmp_path / "state.yaml")
    # Record delivery 2 hours ago
    t["now"] = base - 7200
    state.record_delivery("e0", "test", ["s1"], success=True)

    # Now
    t["now"] = base
    assert state.nudge_count_window(3600) == 0


def test_nudge_budget_failed_delivery_not_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    monkeypatch.setattr(time, "time", lambda: base)

    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e0", "test", [], success=False)
    assert state.nudge_count_window(3600) == 0


def test_nudge_budget_queued_and_inbox_not_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    monkeypatch.setattr(time, "time", lambda: base)
    state = StateManager(tmp_path / "state.yaml")
    state.record_delivery("e0", "maintenance", ["s1"], success=True, queued=True)
    state.record_delivery("e1", "inbox_notify", ["s1"], success=True)
    assert state.nudge_count_window(3600) == 0
    state.record_delivery("e2", "maintenance", ["s1"], success=True)
    assert state.nudge_count_window(3600) == 1


def test_inbox_inflight_expires(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])
    state = StateManager(tmp_path / "state.yaml")
    state.mark_inbox_inflight("inbox", "a.md", "1:2")
    assert state.is_inbox_inflight("inbox", "a.md", "1:2") is True
    t["now"] = base + state.INBOX_INFLIGHT_TIMEOUT_SEC + 1
    # First expiry → awaiting retry (not skip)
    assert state.is_inbox_inflight("inbox", "a.md", "1:2") is False


def test_inbox_inflight_gives_up_after_max_attempts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = 4_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])
    state = StateManager(tmp_path / "state.yaml")
    fp = "1:2"
    for i in range(state.INBOX_INFLIGHT_MAX_ATTEMPTS):
        state.mark_inbox_inflight("inbox", "stuck.md", fp)
        t["now"] = base + (i + 1) * (state.INBOX_INFLIGHT_TIMEOUT_SEC + 1)
        still = state.is_inbox_inflight("inbox", "stuck.md", fp)
        if i + 1 < state.INBOX_INFLIGHT_MAX_ATTEMPTS:
            assert still is False  # allow retry
        else:
            assert still is True  # gave up — treated as processed/skip
    assert state.is_file_processed("inbox", "stuck.md", fp) is True


def test_recent_deliveries_returns_type_and_minutes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = 4_000_000.0
    t = {"now": base}
    monkeypatch.setattr(time, "time", lambda: t["now"])

    state = StateManager(tmp_path / "state.yaml")
    # Record two deliveries 10 and 5 minutes ago
    t["now"] = base - 600
    state.record_delivery("e1", "maintenance", ["s1"], success=True)
    t["now"] = base - 300
    state.record_delivery("e2", "research", ["s1"], success=True)

    t["now"] = base
    recent = state.recent_deliveries(limit=5)
    assert len(recent) == 2
    # Most recent first
    assert recent[0][0] == "research"
    assert abs(recent[0][1] - 5.0) < 0.1
    assert recent[1][0] == "maintenance"
    assert abs(recent[1][1] - 10.0) < 0.1


def test_park_and_due_deferred(tmp_path: Path) -> None:
    from datetime import datetime

    state = StateManager(tmp_path / "state.yaml")
    prefer_until = datetime(2026, 7, 31, 3, 0, 0).timestamp()
    state.park_deferred(
        "idle_engine",
        event_type="maintenance",
        text="hold me",
        source="idle",
        entry_point="idle",
        priority=10,
        preferred_target=None,
        preferred_source="telegram",
        prefer_until=prefer_until,
        preferred_hours=[0, 1, 2],
    )
    assert state.get_deferred("idle_engine") is not None

    # Still waiting (afternoon before prefer_until)
    afternoon = datetime(2026, 7, 30, 14, 0, 0).timestamp()
    assert state.due_deferred(now=afternoon) == []

    # Inside preferred hour
    night = datetime(2026, 7, 31, 1, 0, 0).timestamp()
    due = state.due_deferred(now=night)
    assert len(due) == 1
    assert due[0]["force_asap"] is False

    # Past prefer_until outside window → ASAP
    morning = datetime(2026, 7, 31, 4, 0, 0).timestamp()
    due = state.due_deferred(now=morning)
    assert len(due) == 1
    assert due[0]["force_asap"] is True

    state.clear_deferred("idle_engine")
    assert state.get_deferred("idle_engine") is None
