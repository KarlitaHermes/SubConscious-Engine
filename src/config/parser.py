"""Parse entry points and routing rules from YAML."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.config.models import EntryPoint, HandleConfig, RoutingConfig


def expand_path(value: str) -> Path:
    return Path(os.path.expanduser(value)).resolve()


def parse_handle(raw: dict[str, Any] | None) -> HandleConfig:
    item = raw or {}
    return HandleConfig(
        parser=str(item.get("parser", "auto")),
        handler=str(item.get("handler", "event_file")),
        default_event_type=str(item.get("default_event_type", "custom")),
        default_priority=int(item.get("default_priority", 0)),
    )


def parse_entry_point(item: dict[str, Any]) -> EntryPoint:
    """Parse one entry_points[] item."""
    ep_type = str(item.get("type", "directory"))
    path_raw = item.get("path")
    archive = item.get("archive_dir")
    return EntryPoint(
        id=str(item["id"]),
        type=ep_type,
        enabled=bool(item.get("enabled", True)),
        path=expand_path(path_raw) if path_raw else None,
        poll_interval_seconds=float(item.get("poll_interval_seconds", 5)),
        archive_dir=expand_path(archive) if archive else None,
        host=str(item.get("host", "127.0.0.1")),
        port=int(item.get("port", 8770)),
        api_key=str(item.get("api_key", "")),
        handle=parse_handle(item.get("handle")),
    )


def parse_entry_points(raw: dict[str, Any]) -> list[EntryPoint]:
    """Parse entry_points list, or build from legacy sources block."""
    if raw.get("entry_points"):
        return [parse_entry_point(item) for item in raw["entry_points"]]

    return _legacy_entry_points(raw)


def _legacy_entry_points(raw: dict[str, Any]) -> list[EntryPoint]:
    """Map old sources.file / sources.rest / sources.idle to entry_points."""
    points: list[EntryPoint] = []
    sources = raw.get("sources", {})
    file_raw = sources.get("file", {})
    rest_raw = sources.get("rest", {})

    if file_raw.get("enabled", True):
        path = file_raw.get("directory", "~/.hermes/subconscious-engine/events")
        archive = file_raw.get("archive_dir")
        points.append(
            EntryPoint(
                id="events_drop",
                type="directory",
                enabled=True,
                path=expand_path(path),
                poll_interval_seconds=float(file_raw.get("poll_interval_seconds", 5)),
                archive_dir=expand_path(archive) if archive else None,
                handle=HandleConfig(default_event_type="custom"),
            ),
        )

    if rest_raw.get("enabled", True):
        points.append(
            EntryPoint(
                id="api",
                type="http",
                enabled=True,
                host=str(rest_raw.get("host", "127.0.0.1")),
                port=int(rest_raw.get("port", 8770)),
                api_key=str(rest_raw.get("api_key", "")),
                handle=HandleConfig(default_event_type="custom"),
            ),
        )

    points.append(
        EntryPoint(
            id="idle",
            type="idle",
            enabled=bool(sources.get("idle", True)),
        ),
    )

    return points


def normalize_routing_rule(item: dict[str, Any]) -> dict[str, Any]:
    """Flatten nested match/deliver rules into the internal rule dict."""
    if "match" not in item and "deliver" not in item:
        return dict(item)

    match = item.get("match") or {}
    deliver = item.get("deliver") or {}
    normalized = {
        "name": item.get("name"),
        "event_type": match.get("event_type", match.get("type", "*")),
        "entry_point": match.get("entry_point"),
        "min_event_priority": match.get("min_event_priority", 0),
        **deliver,
    }
    return {k: v for k, v in normalized.items() if v is not None}


def parse_routing(raw: dict[str, Any], default_rules: list[dict[str, Any]]) -> RoutingConfig:
    routing_raw = raw.get("routing") or raw.get("router") or {}
    rules_raw = routing_raw.get("rules") or default_rules
    rules = [normalize_routing_rule(item) for item in rules_raw]
    return RoutingConfig(rules=rules)


def default_routing_rules() -> list[dict[str, Any]]:
    return [
        {
            "name": "maintenance",
            "event_type": "maintenance",
            "target_sources": ["telegram"],
            "max_targets": 1,
            "cooldown_minutes": 60,
            "priority": 10,
        },
        {
            "name": "research",
            "event_type": "research",
            "target_sources": ["telegram"],
            "max_targets": 1,
            "cooldown_minutes": 60,
            "priority": 10,
        },
        {
            "name": "pending_decisions",
            "event_type": "pending_decisions",
            "target_sources": ["telegram"],
            "max_targets": 1,
            "cooldown_minutes": 60,
            "priority": 20,
        },
        {
            "name": "broadcast",
            "event_type": "broadcast",
            "target_sources": ["telegram"],
            "broadcast": True,
            "priority": 5,
        },
        {
            "name": "default",
            "event_type": "*",
            "target_sources": ["telegram"],
            "max_targets": 1,
            "priority": 0,
        },
    ]
