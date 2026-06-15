"""Tests for event models."""

from src.events.models import Event, EventSourceKind


def test_event_from_dict_minimal() -> None:
    event = Event.from_dict({"text": "hello", "event_type": "custom"}, EventSourceKind.REST)
    assert event.text == "hello"
    assert event.event_type == "custom"
    assert event.source == EventSourceKind.REST
    assert event.targets == []
