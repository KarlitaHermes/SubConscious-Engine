"""Shared gate — suppress Hermes notifications when nothing should fire."""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from src.config import Config
from src.config.models import EntryPoint
from src.events.models import Event, EventSourceKind
from src.router.rules import RouteRule, parse_rules, select_rule
from src.state import StateManager

logger = logging.getLogger(__name__)


class SuppressReason(str, Enum):
    """Why an event should not be published or delivered."""

    NO_RULE = "no_rule"
    POLL_SEEN = "poll_seen"
    IN_PROGRESS = "in_progress"
    COOLDOWN = "cooldown"


class NotifyGate:
    """Decide whether an event should reach Hermes (publish + deliver)."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._rules = parse_rules(config.router.rules)

    def check(
        self,
        state: StateManager,
        event: Event,
        *,
        poll_item_key: Optional[str] = None,
    ) -> Optional[SuppressReason]:
        """Return a suppress reason, or None if the event may notify."""
        rule = select_rule(
            self._rules,
            event.event_type,
            event.priority,
            event.entry_point,
        )
        if rule is None:
            return SuppressReason.NO_RULE

        if poll_item_key is not None and event.entry_point:
            if state.is_poll_item_seen(event.entry_point, poll_item_key):
                return SuppressReason.POLL_SEEN

        cooldown_key = event.cooldown_key or event.event_type
        if state.is_task_in_progress(cooldown_key):
            return SuppressReason.IN_PROGRESS

        cooldown_minutes = rule.cooldown_minutes or self._config.idle.cooldown_minutes
        if state.is_in_cooldown(cooldown_minutes, key=cooldown_key):
            return SuppressReason.COOLDOWN

        return None

    def should_notify(
        self,
        state: StateManager,
        event: Event,
        *,
        poll_item_key: Optional[str] = None,
    ) -> bool:
        """Return True when the event should be published or delivered."""
        return self.check(state, event, poll_item_key=poll_item_key) is None

    def log_suppressed(
        self,
        event: Event,
        reason: SuppressReason,
        *,
        poll_item_key: Optional[str] = None,
        source: str = "",
    ) -> None:
        """Emit a debug log for a suppressed event."""
        prefix = f"{source} " if source else ""
        key = event.cooldown_key or event.event_type
        if reason is SuppressReason.POLL_SEEN:
            logger.debug(
                "%sevent type=%s suppressed — poll item seen (%s:%s)",
                prefix,
                event.event_type,
                event.entry_point,
                poll_item_key,
            )
        elif reason is SuppressReason.IN_PROGRESS:
            logger.debug(
                "%sevent type=%s suppressed — task in progress (%s)",
                prefix,
                event.event_type,
                key,
            )
        elif reason is SuppressReason.COOLDOWN:
            logger.debug(
                "%sevent type=%s suppressed — cooldown (%s)",
                prefix,
                event.event_type,
                key,
            )
        else:
            logger.debug(
                "%sevent type=%s suppressed — no applicable rule",
                prefix,
                event.event_type,
            )

    def any_actionable_poll_items(
        self,
        state: StateManager,
        entry_point_id: str,
        items: list[tuple[Event, str]],
    ) -> bool:
        """Return True if any parsed poll item would pass the gate."""
        for event, dedupe_key in items:
            event.entry_point = event.entry_point or entry_point_id
            if self.should_notify(state, event, poll_item_key=dedupe_key):
                return True
        return False

    def should_fetch_poll(self, state: StateManager, entry_point: EntryPoint) -> bool:
        """Skip HTTP fetch when a single-item poll would be blocked anyway."""
        fmt = entry_point.handle.response_format
        if fmt in ("open_meteo", "events_list"):
            return True

        probe = Event(
            text="",
            event_type=entry_point.handle.default_event_type,
            source=EventSourceKind.HTTP_POLL,
            entry_point=entry_point.id,
            priority=entry_point.handle.default_priority,
        )
        reason = self.check(state, probe)
        if reason is not None:
            self.log_suppressed(probe, reason, source=f"http_poll {entry_point.id}")
            return False
        return True

    def resolve_rule(self, event: Event) -> Optional[RouteRule]:
        """Return the routing rule for an event, if any."""
        return select_rule(
            self._rules,
            event.event_type,
            event.priority,
            event.entry_point,
        )

    def cooldown_key(self, event: Event) -> str:
        """Effective cooldown key for an event."""
        return event.cooldown_key or event.event_type

    def cooldown_minutes(self, rule: RouteRule) -> int:
        """Effective cooldown minutes for a rule."""
        return rule.cooldown_minutes or self._config.idle.cooldown_minutes
