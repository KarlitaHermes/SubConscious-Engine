"""Poll vault rules.md and publish events for matched rules."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from src.checks.context import build_vault_context
from src.checks.vault_rules import VaultRulesEngine, resolve_rules_path
from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind
from src.notify_gate import NotifyGate
from src.state import StateManager

logger = logging.getLogger(__name__)


class VaultRulesEventSource:
    """Evaluate rules.md on an interval and publish matched rules as events."""

    def __init__(
        self,
        entry_point: EntryPoint,
        state: StateManager,
        *,
        vault_root: Path,
        inbox_dir: Path | None = None,
        notify_gate: NotifyGate | None = None,
    ) -> None:
        if entry_point.path is None:
            raise ValueError(f"Vault rules entry point {entry_point.id!r} requires path")
        self._entry_point = entry_point
        self._configured_path = entry_point.path
        self._rules_path = resolve_rules_path(entry_point.path)
        self._vault_root = vault_root if entry_point.path.is_dir() else entry_point.path.parent
        self._inbox_dir = inbox_dir
        self._poll_interval = entry_point.poll_interval_seconds
        self._handle = entry_point.handle
        self._state = state
        self._gate = notify_gate
        self._engine = VaultRulesEngine(self._rules_path)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, bus: EventBus) -> None:
        """Start rules evaluation loop."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(bus))
        logger.info(
            "Vault rules source %s evaluating %s every %ss",
            self._entry_point.id,
            self._rules_path,
            self._poll_interval,
        )

    async def stop(self) -> None:
        """Stop the evaluation loop."""
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
                await self._evaluate(bus)
            except Exception:
                logger.exception("Vault rules evaluation error")
            await asyncio.sleep(self._poll_interval)

    async def _evaluate(self, bus: EventBus) -> None:
        context = build_vault_context(
            self._vault_root,
            inbox_dir=self._inbox_dir,
            last_nudge_timestamp=self._state.last_trigger_time or 0.0,
        )
        matches = self._engine.evaluate(
            context,
            rule_last_run=self._state.rule_last_run,
        )
        for match in matches:
            event = Event(
                text=match.prompt,
                event_type=self._handle.default_event_type,
                source=EventSourceKind.FILE,
                entry_point=self._entry_point.id,
                priority=max(match.event_priority, self._handle.default_priority),
                cooldown_key=f"vault_rule:{match.rule_id}",
                metadata={
                    "handler": "vault_rules",
                    "rule_id": match.rule_id,
                    "action_type": match.action_type,
                    "priority": match.priority,
                },
            )
            if self._gate is not None:
                reason = self._gate.check(self._state, event)
                if reason is not None:
                    self._gate.log_suppressed(
                        event,
                        reason,
                        source=f"vault_rules {self._entry_point.id}",
                    )
                    continue
            if await bus.publish(event):
                self._state.record_rule_run(match.rule_id)
                logger.info("Vault rule event published: %s", match.rule_id)
