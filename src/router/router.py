"""Event router — resolves targets and dispatches delivery."""

from __future__ import annotations

import logging
from typing import Optional

from src.config import Config
from src.delivery.sessions import SessionInfo, SessionRegistry
from src.delivery.subconscious import SubConsciousClient
from src.events.models import DeliveryResult, Event
from src.router.rules import RouteRule, parse_rules, select_rule
from src.state import StateManager

logger = logging.getLogger(__name__)

SKIP_SOURCES = frozenset({"cron", "subagent", "api_server"})


class Router:
    """Resolves event targets and delivers to one or more sessions."""

    def __init__(
        self,
        config: Config,
        registry: SessionRegistry,
        delivery: SubConsciousClient,
        state: StateManager,
    ) -> None:
        self._config = config
        self._registry = registry
        self._delivery = delivery
        self._state = state
        self._rules = parse_rules(config.router.rules)

    async def handle(self, event: Event) -> list[DeliveryResult]:
        """Route an event and deliver to resolved session(s)."""
        rule = select_rule(
            self._rules,
            event.event_type,
            event.priority,
            event.entry_point,
        )
        if rule is None:
            logger.info(
                "Event %s type=%s skipped — no applicable rule (time/priority)",
                event.id,
                event.event_type,
            )
            return []

        cooldown_key = event.cooldown_key or event.event_type
        cooldown_minutes = rule.cooldown_minutes or self._config.idle.cooldown_minutes

        if self._state.is_in_cooldown(cooldown_minutes, key=cooldown_key):
            logger.info("Event %s in cooldown (%s)", event.id, cooldown_key)
            return []

        targets = await self._resolve_targets(event, rule)
        if not targets:
            logger.warning("No targets resolved for event %s type=%s", event.id, event.event_type)
            return []

        results = await self._delivery.inject_many(event.text, targets)
        success_count = sum(1 for r in results if r.success)
        self._state.record_delivery(
            event_id=event.id,
            event_type=event.event_type,
            session_ids=[r.session_id for r in results if r.success],
            success=success_count > 0,
            cooldown_key=cooldown_key,
        )
        return results

    async def _resolve_targets(self, event: Event, rule: RouteRule) -> list[SessionInfo]:
        """Resolve target sessions from explicit IDs, hints, and rules."""
        if event.targets:
            sessions = await self._registry.get_sessions_by_ids(event.targets)
            return sessions[: rule.max_targets] if not rule.broadcast else sessions

        if event.preferred_target:
            session = await self._registry.get_session(event.preferred_target)
            if session is not None:
                return [session]

        sources = rule.target_sources or (
            [event.preferred_source] if event.preferred_source else []
        )
        if not sources:
            sources = [self._config.idle.target_source, *self._config.idle.fallback_sources]

        sources = [s for s in sources if s not in SKIP_SOURCES]
        sessions = await self._registry.find_sessions_for_sources(
            sources,
            max_targets=rule.max_targets,
            broadcast=rule.broadcast,
        )
        return sessions
