"""Tests for inbox and vault rule handlers."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.checks.context import build_vault_context
from src.checks.inbox import (
    classify_inbox_file,
    is_standing_file,
    parse_inbox_recipient,
)
from src.checks.vault_rules import VaultRulesEngine, resolve_rules_path
from src.events.bus import EventBus
from src.sources.inbox_watcher import InboxEventSource
from src.sources.vault_rules import VaultRulesEventSource
from src.config.models import EntryPoint, HandleConfig
from src.state import StateManager


def test_is_standing_file() -> None:
    assert is_standing_file("dream-task-v2.md") is True
    assert is_standing_file("email-test.md") is False


def test_parse_inbox_recipient() -> None:
    assert parse_inbox_recipient("kanban-report-weather-2026-09-18-19-face.md") == "face"
    assert parse_inbox_recipient("kanban-report-a4-blocked-2026-09-18-worker.md") == "worker"
    assert parse_inbox_recipient("kanban-report-a0-2026-09-18-dumb.md") == "dumb"
    assert parse_inbox_recipient("kanban-report-b3-2026-09-18-musickarla.md") == "musickarla"
    # Bare name / mid-name "face" is NOT a recipient token
    assert parse_inbox_recipient("kanban-report-weather-2026-09-18-19.md") == "face"
    assert parse_inbox_recipient("kanban-report-weather-face-20260918083114.md") == "face"
    assert parse_inbox_recipient("news-digest-2026-09-18.md") == "face"


def test_classify_notify_prefix(tmp_path: Path) -> None:
    path = tmp_path / "news-digest-june.md"
    path.write_text("# digest\n", encoding="utf-8")
    result = classify_inbox_file(path)
    assert result is not None
    assert result.disposition == "notify"
    assert result.event_type == "inbox_notify"
    assert result.recipient == "face"


def test_classify_recipient_suffix(tmp_path: Path) -> None:
    path = tmp_path / "kanban-report-music-2026-09-18-worker.md"
    path.write_text("# music\n", encoding="utf-8")
    result = classify_inbox_file(path)
    assert result is not None
    assert result.recipient == "worker"
    assert result.event_type == "inbox_notify"


def test_classify_unknown_file_needs_review(tmp_path: Path) -> None:
    path = tmp_path / "mystery-drop.md"
    path.write_text("something new", encoding="utf-8")
    result = classify_inbox_file(path)
    assert result is not None
    assert result.disposition == "review"


def test_build_vault_context_report_count(tmp_path: Path) -> None:
    reports = tmp_path / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    (reports / "a.md").write_text("one", encoding="utf-8")
    (reports / "b.md").write_text("two", encoding="utf-8")

    ctx = build_vault_context(tmp_path)
    assert ctx["report_count"] == 2


def test_vault_rules_engine_matches_report_rule(tmp_path: Path) -> None:
    rules = tmp_path / "rules.md"
    rules.write_text(
        "## Rule 3: Report Consolidation\n"
        "**Condition:** >5 reports in `Projects/Maintenance/Reports/`\n"
        "**Action:** Archive one-liners\n"
        "**Priority:** LOW\n",
        encoding="utf-8",
    )
    reports = tmp_path / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    for idx in range(6):
        (reports / f"r{idx}.md").write_text("x", encoding="utf-8")

    engine = VaultRulesEngine(rules)
    matches = engine.evaluate(build_vault_context(tmp_path))
    assert len(matches) == 1
    assert matches[0].rule_id == "Report Consolidation"


def test_resolve_rules_path_from_vault_root(tmp_path: Path) -> None:
    rules = tmp_path / "Projects" / "Maintenance" / "rules.md"
    rules.parent.mkdir(parents=True)
    rules.write_text("## Rule 1: Test\n**Condition:** x\n", encoding="utf-8")
    assert resolve_rules_path(tmp_path) == rules


@pytest.mark.asyncio
async def test_inbox_source_publishes_new_file(tmp_path: Path) -> None:
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    (inbox_dir / "email-test.md").write_text("Please review this email", encoding="utf-8")

    state = StateManager(tmp_path / "state.yaml")
    entry_point = EntryPoint(
        id="inbox",
        type="directory",
        path=inbox_dir,
        poll_interval_seconds=1,
        handle=HandleConfig(handler="inbox", default_event_type="inbox_item"),
    )
    source = InboxEventSource(entry_point, state, vault_root=tmp_path)
    bus = EventBus()
    await source._scan_inbox(bus)

    events = []
    bus.close()
    async for event in bus.consume():
        events.append(event)

    assert len(events) == 1
    assert events[0].entry_point == "inbox"
    assert events[0].event_type == "inbox_item"
    assert events[0].metadata.get("file_fingerprint")
    # Processed only after delivery — publish alone must not mark (Bug A).
    assert state.is_file_processed("inbox", "email-test.md") is False


@pytest.mark.asyncio
async def test_inbox_source_skips_already_processed(tmp_path: Path) -> None:
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    path = inbox_dir / "email-test.md"
    path.write_text("again", encoding="utf-8")
    st = path.stat()
    fingerprint = f"{st.st_mtime_ns}:{st.st_size}"

    state = StateManager(tmp_path / "state.yaml")
    state.mark_file_processed("inbox", "email-test.md", fingerprint)
    entry_point = EntryPoint(id="inbox", type="directory", path=inbox_dir)
    source = InboxEventSource(
        entry_point,
        state,
        vault_root=tmp_path,
    )
    bus = EventBus()
    await source._scan_inbox(bus)
    bus.close()

    events = []
    async for event in bus.consume():
        events.append(event)
    assert events == []


@pytest.mark.asyncio
async def test_inbox_source_renotifies_on_rewrite(tmp_path: Path) -> None:
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir()
    path = inbox_dir / "kanban-report-weather-test.md"
    path.write_text("first", encoding="utf-8")
    st = path.stat()
    fingerprint = f"{st.st_mtime_ns}:{st.st_size}"

    state = StateManager(tmp_path / "state.yaml")
    state.mark_file_processed("inbox", path.name, fingerprint)
    entry_point = EntryPoint(
        id="inbox",
        type="directory",
        path=inbox_dir,
        handle=HandleConfig(handler="inbox", default_event_type="inbox_item"),
    )
    source = InboxEventSource(entry_point, state, vault_root=tmp_path)

    path.write_text("second — corrected", encoding="utf-8")
    bus = EventBus()
    await source._scan_inbox(bus)
    bus.close()
    events = []
    async for event in bus.consume():
        events.append(event)
    assert len(events) == 1
    assert events[0].event_type == "inbox_notify"


@pytest.mark.asyncio
async def test_vault_rules_source_publishes_match(tmp_path: Path) -> None:
    rules = tmp_path / "rules.md"
    rules.write_text(
        "## Rule 1: Memory\n"
        "**Condition:** memory > 10 char\n"
        "**Action:** Audit memory\n"
        "**Priority:** MEDIUM\n",
        encoding="utf-8",
    )
    (tmp_path / "memory.md").write_text("x" * 20, encoding="utf-8")

    state = StateManager(tmp_path / "state.yaml")
    entry_point = EntryPoint(
        id="vault_rules",
        type="directory",
        path=rules,
        poll_interval_seconds=60,
        handle=HandleConfig(handler="vault_rules", default_event_type="vault_rule"),
    )
    source = VaultRulesEventSource(entry_point, state, vault_root=tmp_path)
    bus = EventBus()
    await source._evaluate(bus)

    events = []
    bus.close()
    async for event in bus.consume():
        events.append(event)

    assert len(events) == 1
    assert events[0].event_type == "vault_rule"
    assert events[0].metadata["rule_id"] == "Memory"
    assert "rule_last_run" in state._data
