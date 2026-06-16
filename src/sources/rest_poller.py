"""Outbound HTTP polling — fetch external APIs and publish events."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.notify_gate import NotifyGate
from src.sources.rest_poll_parse import parse_poll_body
from src.state import StateManager

logger = logging.getLogger(__name__)


class RestPollEventSource:
    """Poll a remote HTTP endpoint and publish new items as events."""

    def __init__(
        self,
        entry_point: EntryPoint,
        state: StateManager,
        http: aiohttp.ClientSession,
        *,
        notify_gate: NotifyGate | None = None,
    ) -> None:
        if not entry_point.url:
            raise ValueError(f"http_poll entry point {entry_point.id!r} requires url")
        self._entry_point = entry_point
        self._state = state
        self._http = http
        self._gate = notify_gate
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, bus: EventBus) -> None:
        """Start the poll loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(bus))
        logger.info(
            "HTTP poll source %s polling %s every %ss",
            self._entry_point.id,
            self._entry_point.url,
            self._entry_point.poll_interval_seconds,
        )

    async def stop(self) -> None:
        """Stop the poll loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self, bus: EventBus) -> None:
        while self._running:
            try:
                await self._poll_once(bus)
            except Exception:
                logger.exception("HTTP poll error for %s", self._entry_point.id)
            await asyncio.sleep(self._entry_point.poll_interval_seconds)

    async def _poll_once(self, bus: EventBus) -> None:
        """Fetch the remote URL once and publish unseen events."""
        if self._gate is not None and not self._gate.should_fetch_poll(
            self._state,
            self._entry_point,
        ):
            return

        headers = dict(self._entry_point.headers)
        if self._entry_point.api_key:
            headers.setdefault("Authorization", f"Bearer {self._entry_point.api_key}")

        async with self._http.request(
            self._entry_point.method,
            self._entry_point.url,
            headers=headers,
        ) as response:
            if response.status >= 400:
                body = await response.text()
                logger.warning(
                    "HTTP poll %s returned %s: %s",
                    self._entry_point.id,
                    response.status,
                    body[:200],
                )
                return
            body = await response.text()

        parsed = parse_poll_body(
            body,
            entry_point_id=self._entry_point.id,
            handle=self._entry_point.handle,
        )
        if self._gate is not None and not self._gate.any_actionable_poll_items(
            self._state,
            self._entry_point.id,
            parsed,
        ):
            logger.debug(
                "HTTP poll %s skipped publish — no actionable items",
                self._entry_point.id,
            )
            return

        for event, dedupe_key in parsed:
            if self._gate is not None:
                reason = self._gate.check(self._state, event, poll_item_key=dedupe_key)
                if reason is not None:
                    self._gate.log_suppressed(
                        event,
                        reason,
                        poll_item_key=dedupe_key,
                        source=f"http_poll {self._entry_point.id}",
                    )
                    continue
            elif self._state.is_poll_item_seen(self._entry_point.id, dedupe_key):
                continue
            if await bus.publish(event):
                self._state.mark_poll_item_seen(self._entry_point.id, dedupe_key)
                logger.info(
                    "HTTP poll %s published event %s (key=%s)",
                    self._entry_point.id,
                    event.id,
                    dedupe_key,
                )
