"""Idle detection as an internal event source."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from src.checks.prompts import (
    build_maintenance_prompt,
    build_pending_decisions_prompt,
    build_research_prompt,
)
from src.config import Config
from src.delivery.sessions import SessionRegistry
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind
from src.notify_gate import NotifyGate
from src.signals.session import get_last_human_activity
from src.state import StateManager

logger = logging.getLogger(__name__)

IDLE_COOLDOWN_KEY = "idle_engine"
DECISIONS_COOLDOWN_KEY = "pending_decisions"


class IdleEventSource:
    """Poll for idle sessions, wake events, and emit nudges."""

    def __init__(
        self,
        config: Config,
        registry: SessionRegistry,
        state: StateManager,
        entry_point_id: str = "idle",
        *,
        notify_gate: NotifyGate | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._state = state
        self._entry_point_id = entry_point_id
        self._gate = notify_gate or NotifyGate(config)
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, bus: EventBus) -> None:
        """Start idle polling."""
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(bus))
        logger.info(
            "Idle event source started (threshold=%dm, cooldown=%dm)",
            self._config.idle.threshold_minutes,
            self._config.idle.cooldown_minutes,
        )

    async def stop(self) -> None:
        """Stop idle polling."""
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
                logger.exception("Idle source evaluation error")
            await asyncio.sleep(self._config.poll_interval_seconds)

    async def _evaluate(self, bus: EventBus) -> None:
        session = await self._registry.find_best_session(
            self._config.idle.target_source,
            self._config.idle.fallback_sources,
        )
        if session is None:
            return

        last_activity = await get_last_human_activity(
            self._config.gateway.url,
            self._config.gateway.api_key,
            session.id,
        )
        effective_activity = self._effective_activity(last_activity)

        await self._maybe_emit_pending_decisions(bus, session, effective_activity)

        currently_idle = self._is_idle(effective_activity)
        if currently_idle:
            self._state.set_idle_period_active(True)
        self._state.update_observed_activity(effective_activity)

        if not currently_idle:
            return

        event_type = self._state.next_idle_event_type()
        probe = Event(
            text="",
            event_type=event_type,
            source=EventSourceKind.IDLE,
            entry_point=self._entry_point_id,
            cooldown_key=IDLE_COOLDOWN_KEY,
        )
        reason = self._gate.check(self._state, probe)
        if reason is not None:
            self._gate.log_suppressed(probe, reason, source="idle")
            return

        threshold = self._config.idle.threshold_minutes
        vault = self._config.idle.vault_root

        if event_type == "maintenance":
            text = build_maintenance_prompt(vault, threshold)
        else:
            text = build_research_prompt(vault, threshold)

        count = self._state.record_idle_trigger()
        logger.info("Idle trigger #%d → %s", count, event_type)

        event = Event(
            text=text,
            event_type=event_type,
            source=EventSourceKind.IDLE,
            entry_point=self._entry_point_id,
            preferred_target=session.id,
            preferred_source=session.source,
            cooldown_key=IDLE_COOLDOWN_KEY,
            metadata={
                "idle_minutes": self._idle_minutes(effective_activity),
                "idle_trigger_count": count,
            },
        )
        await bus.publish(event)

    async def _maybe_emit_pending_decisions(
        self,
        bus: EventBus,
        session,
        last_activity: Optional[float],
    ) -> None:
        """Emit a wake nudge when Rev returns after an extended idle period."""
        if last_activity is None:
            return
        if not self._state.idle_period_active:
            return

        grace = self._config.idle.wake_grace_minutes
        minutes_since_activity = (time.time() - last_activity) / 60
        if minutes_since_activity > grace:
            return

        self._state.set_idle_period_active(False)

        probe = Event(
            text="",
            event_type="pending_decisions",
            source=EventSourceKind.IDLE,
            entry_point=self._entry_point_id,
            cooldown_key=DECISIONS_COOLDOWN_KEY,
            priority=5,
        )
        reason = self._gate.check(self._state, probe)
        if reason is not None:
            self._gate.log_suppressed(probe, reason, source="idle")
            return

        prompt = build_pending_decisions_prompt(
            self._config.idle.vault_root,
            idle_minutes=self._config.idle.threshold_minutes,
            since_timestamp=self._state.last_decisions_nudge,
        )
        if prompt is None:
            return

        logger.info("Wake detected — pending decisions nudge for session %s", session.id)
        event = Event(
            text=prompt,
            event_type="pending_decisions",
            source=EventSourceKind.IDLE,
            entry_point=self._entry_point_id,
            preferred_target=session.id,
            preferred_source=session.source,
            cooldown_key=DECISIONS_COOLDOWN_KEY,
            priority=5,
        )
        if await bus.publish(event):
            self._state.record_decisions_nudge()

    def _effective_activity(self, last_human: Optional[float]) -> Optional[float]:
        """Latest of human chat or agent ack — agent handling counts as activity."""
        agent = self._state.last_agent_handled
        if last_human is None:
            return agent
        if agent is None:
            return last_human
        return max(last_human, agent)

    def _is_idle(self, last_activity: Optional[float]) -> bool:
        if last_activity is None:
            return True
        elapsed = time.time() - last_activity
        return elapsed > self._config.idle.threshold_minutes * 60

    def _idle_minutes(self, last_activity: Optional[float]) -> float:
        if last_activity is None:
            return float("inf")
        return max(0.0, (time.time() - last_activity) / 60)
