"""Tests for music curation due detection."""

from pathlib import Path

from src.checks.music_task import music_curation_due, resolve_maintenance_task_id


def test_music_due_from_tasks_md(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "src.checks.music_task._DONE_FLAG",
        tmp_path / "missing-flag.json",
    )
    vault = tmp_path / "vault"
    tasks = vault / "Projects" / "Maintenance"
    tasks.mkdir(parents=True)
    (tasks / "tasks.md").write_text(
        "## Music\n"
        "- [ ] Daily music curation — pick genre **Last done:** 2026-07-29 **(daily)**\n",
        encoding="utf-8",
    )
    from datetime import datetime

    now = datetime(2026, 7, 30, 3, 0, 0)
    assert music_curation_due(vault, now=now) is True
    assert resolve_maintenance_task_id(vault, now=now) == "music_curation"


def test_music_not_due_when_done_today(tmp_path: Path, monkeypatch) -> None:
    flag = tmp_path / ".daily_music_done"
    flag.write_text('{"last_done": "2026-07-30"}', encoding="utf-8")
    monkeypatch.setattr("src.checks.music_task._DONE_FLAG", flag)
    vault = tmp_path / "vault"
    tasks = vault / "Projects" / "Maintenance"
    tasks.mkdir(parents=True)
    (tasks / "tasks.md").write_text(
        "- [x] Daily music curation **Last done:** 2026-07-29 **(daily)**\n",
        encoding="utf-8",
    )
    from datetime import datetime

    now = datetime(2026, 7, 30, 3, 0, 0)
    assert music_curation_due(vault, now=now) is False
    assert resolve_maintenance_task_id(vault, now=now) is None
