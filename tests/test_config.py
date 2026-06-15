"""Tests for configuration loading."""

from pathlib import Path

import pytest

from src.config import CONFIG_ENV_VAR, load_config, resolve_config_path
from src.config.parser import normalize_routing_rule, parse_entry_points


def test_resolve_config_path_explicit() -> None:
    path = resolve_config_path(Path("/tmp/custom.yaml"))
    assert path == Path("/tmp/custom.yaml")


def test_resolve_config_path_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_ENV_VAR, "~/my-config.yaml")
    path = resolve_config_path()
    assert str(path).endswith("my-config.yaml")


def test_load_test_config_profile() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    test_config = repo_root / "config.test.yaml"
    config = load_config(test_config)

    idle_ep = next(ep for ep in config.entry_points if ep.type == "idle")
    assert idle_ep.enabled is False

    rest_ep = next(ep for ep in config.entry_points if ep.type == "http")
    assert rest_ep.port == 8771

    file_ep = next(ep for ep in config.entry_points if ep.type == "directory")
    assert file_ep.poll_interval_seconds == 2

    assert config.poll_interval_seconds == 120
    assert str(config.state.file).endswith("state.test.yaml")
    assert str(config.logging.file).endswith("subconscious-engine-test.log")
    assert len(config.routing.rules) >= 4

    alert_rule = next(r for r in config.routing.rules if r.get("event_type") == "alert")
    assert alert_rule["min_event_priority"] == 10
    assert alert_rule["priority"] == 50


def test_parse_entry_points_explicit() -> None:
    raw = {
        "entry_points": [
            {
                "id": "inbox",
                "type": "directory",
                "path": "/tmp/inbox",
                "handle": {
                    "handler": "inbox",
                    "default_event_type": "inbox_item",
                },
            },
        ],
    }
    points = parse_entry_points(raw)
    assert len(points) == 1
    assert points[0].id == "inbox"
    assert points[0].handle.handler == "inbox"
    assert points[0].handle.default_event_type == "inbox_item"


def test_normalize_routing_rule_match_deliver() -> None:
    normalized = normalize_routing_rule(
        {
            "name": "idle_maintenance",
            "match": {"event_type": "maintenance", "entry_point": "idle"},
            "deliver": {"target_sources": ["telegram"], "max_targets": 1},
        },
    )
    assert normalized["event_type"] == "maintenance"
    assert normalized["entry_point"] == "idle"
    assert normalized["target_sources"] == ["telegram"]
