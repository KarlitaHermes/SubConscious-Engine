"""Tests for file event source parsing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.events.models import EventSourceKind
from src.sources.file_watcher import FileEventSource


@pytest.fixture
def file_source(tmp_path: Path) -> FileEventSource:
    from src.config.models import EntryPoint

    return FileEventSource(
        EntryPoint(
            id="events_drop",
            type="directory",
            path=tmp_path / "events",
            archive_dir=tmp_path / "processed",
        ),
    )


def test_parse_json_file(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "event.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "text": "hello from json",
                "event_type": "alert",
                "preferred_target": "sess_1",
            }
        ),
        encoding="utf-8",
    )
    event = file_source._parse_file(path)
    assert event is not None
    assert event.text == "hello from json"
    assert event.event_type == "alert"
    assert event.source == EventSourceKind.FILE
    assert event.preferred_target == "sess_1"
    assert event.entry_point == "events_drop"
    assert event.metadata["file"] == "event.json"


def test_parse_yaml_file(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "event.yaml"
    path.parent.mkdir()
    path.write_text(
        "text: hello from yaml\nevent_type: custom\n",
        encoding="utf-8",
    )
    event = file_source._parse_file(path)
    assert event is not None
    assert event.text == "hello from yaml"
    assert event.event_type == "custom"


def test_parse_txt_file(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "note.txt"
    path.parent.mkdir()
    path.write_text("plain text message", encoding="utf-8")
    event = file_source._parse_file(path)
    assert event is not None
    assert event.text == "plain text message"
    assert event.event_type == "custom"
    assert event.source == EventSourceKind.FILE


def test_parse_empty_file_returns_none(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "empty.json"
    path.parent.mkdir()
    path.write_text("   \n", encoding="utf-8")
    assert file_source._parse_file(path) is None


def test_parse_invalid_json_returns_none(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "bad.json"
    path.parent.mkdir()
    path.write_text("{not json", encoding="utf-8")
    assert file_source._parse_file(path) is None


def test_parse_json_array_returns_none(file_source: FileEventSource, tmp_path: Path) -> None:
    path = tmp_path / "events" / "array.json"
    path.parent.mkdir()
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert file_source._parse_file(path) is None


def test_archive_file_moves_to_processed(file_source: FileEventSource, tmp_path: Path) -> None:
    src = tmp_path / "events" / "done.json"
    src.parent.mkdir(parents=True)
    (tmp_path / "processed").mkdir(parents=True)
    src.write_text("{}", encoding="utf-8")
    file_source._archive_file(src)
    assert not src.exists()
    assert (tmp_path / "processed" / "done.json").exists()


def test_archive_file_collision_adds_suffix(file_source: FileEventSource, tmp_path: Path) -> None:
    src = tmp_path / "events" / "dup.json"
    src.parent.mkdir(parents=True)
    (tmp_path / "processed").mkdir(parents=True)
    (tmp_path / "processed" / "dup.json").write_text("{}", encoding="utf-8")
    src.write_text('{"text":"x"}', encoding="utf-8")
    file_source._archive_file(src)
    assert not src.exists()
    assert list((tmp_path / "processed").glob("dup*.json"))
