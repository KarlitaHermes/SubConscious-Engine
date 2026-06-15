"""Tests for outbound HTTP poll response parsing."""

from __future__ import annotations

from src.config.models import HandleConfig
from src.events.models import EventSourceKind
from src.sources.rest_poll_parse import dedupe_key_for_item, parse_poll_body


def test_parse_events_list_root_array() -> None:
    body = '[{"id":"e1","text":"hello","event_type":"alert"}]'
    handle = HandleConfig(default_event_type="custom")
    parsed = parse_poll_body(body, entry_point_id="poll", handle=handle)
    assert len(parsed) == 1
    event, key = parsed[0]
    assert event.text == "hello"
    assert event.event_type == "alert"
    assert event.source == EventSourceKind.HTTP_POLL
    assert event.entry_point == "poll"
    assert key == "e1"


def test_parse_events_list_nested_key() -> None:
    body = '{"events":[{"id":"n1","text":"nested"}]}'
    handle = HandleConfig(items_key="events", default_event_type="custom")
    parsed = parse_poll_body(body, entry_point_id="poll", handle=handle)
    assert len(parsed) == 1
    assert parsed[0][0].text == "nested"


def test_parse_single_event() -> None:
    body = '{"id":"solo","text":"one shot","event_type":"custom"}'
    handle = HandleConfig(response_format="single_event", default_event_type="fallback")
    parsed = parse_poll_body(body, entry_point_id="poll", handle=handle)
    assert len(parsed) == 1
    assert parsed[0][0].text == "one shot"
    assert parsed[0][1] == "solo"


def test_parse_text_response() -> None:
    body = "plain text alert"
    handle = HandleConfig(response_format="text", default_event_type="alert")
    parsed = parse_poll_body(body, entry_point_id="poll", handle=handle)
    assert len(parsed) == 1
    assert parsed[0][0].text == "plain text alert"
    assert parsed[0][0].event_type == "alert"


def test_skips_items_without_text() -> None:
    body = '[{"id":"x"},{"id":"y","text":"ok"}]'
    handle = HandleConfig()
    parsed = parse_poll_body(body, entry_point_id="poll", handle=handle)
    assert len(parsed) == 1
    assert parsed[0][0].text == "ok"


def test_dedupe_key_falls_back_to_hash() -> None:
    key = dedupe_key_for_item({"text": "same", "event_type": "custom"}, "id")
    assert key.startswith("hash:")
