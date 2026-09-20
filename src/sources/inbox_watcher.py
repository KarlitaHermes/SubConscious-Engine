"""Watch COMMS/Inbox for new markdown files."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.checks.inbox import build_inbox_prompt, classify_inbox_file
from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind
from src.notify_gate import NotifyGate
from src.state import StateManager

logger = logging.getLogger(__name__)


class InboxEventSource:
    """Poll an inbox directory and publish events for new markdown files."""

    def __init__(
        self,
        entry_point: EntryPoint,
        state: StateManager,
        *,
        vault_root: Path,
        notify_gate: NotifyGate | None = None,
    ) -> None:
        if entry_point.path is None:
            raise ValueError(f"Inbox entry point {entry_point.id!r} requires path")
        self._entry_point = entry_point
        self._directory = entry_point.path
        self._poll_interval = entry_point.poll_interval_seconds
        self._handle = entry_point.handle
        self._state = state
        self._vault_root = vault_root
        self._gate = notify_gate
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, bus: EventBus) -> None:
        """Start polling the inbox."""
        self._directory.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(bus))
        logger.info("Inbox event source %s watching %s", self._entry_point.id, self._directory)

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
                await self._scan_inbox(bus)
            except Exception:
                logger.exception("Inbox source scan error")
            await asyncio.sleep(self._poll_interval)

    async def _scan_inbox(self, bus: EventBus) -> None:
        for path in sorted(self._directory.glob("*.md")):
            if not path.is_file():
                continue
            try:
                st = path.stat()
                fingerprint = f"{st.st_mtime_ns}:{st.st_size}"
            except OSError:
                continue
            if self._state.is_file_processed(self._entry_point.id, path.name, fingerprint):
                continue
            # Queued inject awaiting surface — do not republish until flush timeout.
            if self._state.is_inbox_inflight(
                self._entry_point.id, path.name, fingerprint
            ):
                continue

            classification = classify_inbox_file(
                path,
                default_event_type=self._handle.default_event_type,
            )
            if classification is None:
                continue

            event = Event(
                text=build_inbox_prompt(path, classification, self._vault_root),
                event_type=classification.event_type,
                source=EventSourceKind.FILE,
                entry_point=self._entry_point.id,
                priority=max(classification.priority, self._handle.default_priority),
                cooldown_key=f"inbox:{classification.filename}",
                metadata={
                    "file": path.name,
                    "file_fingerprint": fingerprint,
                    "handler": "inbox",
                    "disposition": classification.disposition,
                    "vault_dest": classification.vault_dest,
                    "inbox_recipient": classification.recipient,
                },
            )
            if self._gate is not None:
                reason = self._gate.check(self._state, event)
                if self._gate.blocks_publish(reason):
                    assert reason is not None
                    self._gate.log_suppressed(
                        event,
                        reason,
                        source=f"inbox {self._entry_point.id}",
                    )
                    continue
            # Do NOT mark processed here — router commits after delivery succeeds.
            # Marking on publish caused permanent loss when delivery then suppressed (Bug A).
            if await bus.publish(event):
                logger.info(
                    "Inbox event published for %s (%s) — pending delivery",
                    path.name,
                    classification.disposition,
                )
