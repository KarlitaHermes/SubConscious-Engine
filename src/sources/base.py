"""Event source protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.events.bus import EventBus


@runtime_checkable
class EventSource(Protocol):
    """Async event producer that publishes to the bus."""

    async def start(self, bus: EventBus) -> None:
        """Start producing events (runs until cancelled)."""
        ...

    async def stop(self) -> None:
        """Graceful shutdown."""
        ...
