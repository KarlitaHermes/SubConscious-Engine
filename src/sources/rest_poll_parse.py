"""Parse HTTP poll responses into events."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.config.models import HandleConfig
from src.events.models import Event, EventSourceKind
from src.sources.open_meteo import parse_open_meteo_forecast


def dedupe_key_for_item(item: dict[str, Any], id_field: str) -> str:
    """Return a stable deduplication key for a poll response item."""
    raw_id = item.get(id_field) or item.get("id")
    if raw_id is not None and str(raw_id).strip():
        return str(raw_id)
    text = str(item.get("text", ""))
    event_type = str(item.get("event_type", item.get("type", "")))
    digest = hashlib.sha256(f"{event_type}:{text}".encode()).hexdigest()[:16]
    return f"hash:{digest}"


def parse_poll_body(
    body: str,
    *,
    entry_point_id: str,
    handle: HandleConfig,
) -> list[tuple[Event, str]]:
    """Parse an HTTP response body into events and dedupe keys.

    Returns:
        List of (Event, dedupe_key) tuples. Invalid items are skipped.
    """
    if handle.response_format == "text":
        text = body.strip()
        if not text:
            return []
        event = Event(
            text=text,
            event_type=handle.default_event_type,
            source=EventSourceKind.HTTP_POLL,
            entry_point=entry_point_id,
            priority=handle.default_priority,
            metadata={"handler": "http_poll", "response_format": "text"},
        )
        key = dedupe_key_for_item({"text": text}, handle.id_field)
        return [(event, key)]

    if handle.response_format == "open_meteo":
        return parse_open_meteo_forecast(
            body,
            entry_point_id=entry_point_id,
            handle=handle,
        )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    if handle.response_format == "single_event":
        items = [data] if isinstance(data, dict) else []
    else:
        items = _extract_items(data, handle.items_key)

    results: list[tuple[Event, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if not str(item.get("text", "")).strip():
            continue
        event = Event.from_dict(item, EventSourceKind.HTTP_POLL)
        event.entry_point = event.entry_point or entry_point_id
        if "event_type" not in item and "type" not in item:
            event.event_type = handle.default_event_type
        if "priority" not in item:
            event.priority = handle.default_priority
        event.metadata.setdefault("handler", "http_poll")
        key = dedupe_key_for_item(item, handle.id_field)
        results.append((event, key))
    return results


def _extract_items(data: Any, items_key: str) -> list[Any]:
    """Extract a list of event dicts from parsed JSON."""
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return []
    if items_key:
        nested = data.get(items_key)
        return nested if isinstance(nested, list) else []
    for key in ("events", "items", "data"):
        nested = data.get(key)
        if isinstance(nested, list):
            return nested
    return []
