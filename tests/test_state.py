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
