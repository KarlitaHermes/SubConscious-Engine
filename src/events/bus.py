"""Async event bus connecting sources to the router."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from src.events.models import Event

logger = logging.getLogger(__name__)


class EventBus:
    """Priority async queue for inbound events (higher priority first)."""

    def __init__(self, maxsize: int = 256) -> None:
        self._queue: asyncio.PriorityQueue[tuple[int, int, Event]] = asyncio.PriorityQueue(
            maxsize=maxsize,
        )
        self._closed = False
        self._sequence = 0

    async def publish(self, event: Event) -> bool:
        """Enqueue an event. Returns False if the bus is closed or full."""
        if self._closed:
            logger.warning("Event bus closed; dropping event %s", event.id)
            return False
        try:
            self._sequence += 1
            # Lower sort key = dequeued first: negate priority, preserve FIFO via sequence.
            self._queue.put_nowait((-event.priority, self._sequence, event))
            logger.debug(
                "Published event %s type=%s priority=%d",
                event.id,
                event.event_type,
                event.priority,
            )
            return True
        except asyncio.QueueFull:
            logger.error("Event bus full; dropping event %s", event.id)
            return False

    async def consume(self) -> AsyncIterator[Event]:
        """Yield events until the bus is closed and drained."""
        while True:
            if self._closed and self._queue.empty():
                break
            try:
                _prio, _seq, event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            yield event
            self._queue.task_done()

    def close(self) -> None:
        """Stop accepting new events."""
        self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def qsize(self) -> int:
        return self._queue.qsize()
