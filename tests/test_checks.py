"""Tests for vault file checks and prompts."""

from __future__ import annotations

import time
from pathlib import Path

from src.checks.decisions import get_pending_decisions
from src.checks.prompts import (
    build_maintenance_prompt,
    build_pending_decisions_prompt,
    build_research_prompt,
)


def test_get_pending_decisions_from_report(tmp_path: Path) -> None:
    reports = tmp_path / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    report = reports / "test-report.md"
    report.write_text("Some text\n⚠️ Needs Rev to decide on vault merge\n", encoding="utf-8")

    items = get_pending_decisions(tmp_path, since_timestamp=0.0)
    assert len(items) == 1
    assert "test-report.md" in items[0]


def test_get_pending_decisions_skips_old_files(tmp_path: Path) -> None:
    reports = tmp_path / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    report = reports / "old.md"
    report.write_text("⚠️ stale", encoding="utf-8")
    old_time = time.time() - 90000
    import os

    os.utime(report, (old_time, old_time))

    items = get_pending_decisions(tmp_path, since_timestamp=0.0)
    assert items == []


def test_build_pending_decisions_prompt_none_when_empty(tmp_path: Path) -> None:
    assert build_pending_decisions_prompt(tmp_path, idle_minutes=45.0) is None


def test_build_pending_decisions_prompt_with_items(tmp_path: Path) -> None:
    reports = tmp_path / "Projects" / "Maintenance" / "Reports"
    reports.mkdir(parents=True)
    (reports / "r.md").write_text("ACTION REQUIRED: pick a color\n", encoding="utf-8")

    prompt = build_pending_decisions_prompt(tmp_path, idle_minutes=35.0)
    assert prompt is not None
    assert "[SUBCONSCIOUS]" in prompt
    assert "ACTION REQUIRED" in prompt


def test_build_maintenance_prompt_includes_task_path(tmp_path: Path) -> None:
    text = build_maintenance_prompt(tmp_path, threshold_minutes=30)
    assert "[SUBCONSCIOUS]" in text
    assert "Maintenance/tasks.md" in text
    assert "Actions: [execute_task, skip_all, defer]" in text


def test_build_research_prompt_includes_research_path(tmp_path: Path) -> None:
    text = build_research_prompt(tmp_path, threshold_minutes=30)
    assert "[SUBCONSCIOUS]" in text
    assert "web-research-tasks.md" in text
