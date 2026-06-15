"""Tests for priority event bus."""

import pytest

from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind


@pytest.mark.asyncio
async def test_bus_priority_ordering() -> None:
    bus = EventBus()
    low = Event(text="low", event_type="a", source=EventSourceKind.REST, priority=1)
    high = Event(text="high", event_type="a", source=EventSourceKind.REST, priority=100)
    mid = Event(text="mid", event_type="a", source=EventSourceKind.REST, priority=50)

    await bus.publish(low)
    await bus.publish(high)
    await bus.publish(mid)
    bus.close()

    received = []
    async for event in bus.consume():
        received.append(event.text)

    assert received == ["high", "mid", "low"]
