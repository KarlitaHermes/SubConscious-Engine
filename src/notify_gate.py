"""Shared gate — suppress Hermes notifications when nothing should fire."""

from __future__ import annotations

import logging
from datetime import datetime
from enum import Enum
from typing import Optional

from src.config import Config
from src.config.models import EntryPoint
from src.events.models import Event, EventSourceKind
from src.router.rules import RouteRule, parse_rules, select_rule
from src.router.window import (
    FORCE_ASAP_META,
    should_defer_for_preferred_window,
    window_bounds_containing,
)
from src.state import StateManager

logger = logging.getLogger(__name__)


class SuppressReason(str, Enum):
    """Why an event should not be published or delivered."""

    NO_RULE = "no_rule"
    POLL_SEEN = "poll_seen"
    IN_PROGRESS = "in_progress"
    COOLDOWN = "cooldown"
    NUDGE_BUDGET = "nudge_budget"
    DEFER_PREFERRED_WINDOW = "defer_preferred_window"


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
        now: Optional[datetime] = None,
    ) -> Optional[SuppressReason]:
        """Return a suppress/defer reason, or None if the event may deliver now."""
        rule = select_rule(
            self._rules,
            event.event_type,
            event.priority,
            event.entry_point,
            now=now,
            task_id=event.task_id,
        )
        if rule is None:
            return SuppressReason.NO_RULE

        if poll_item_key is not None and event.entry_point:
            if state.is_poll_item_seen(event.entry_point, poll_item_key):
                return SuppressReason.POLL_SEEN

        cooldown_key = event.cooldown_key or event.event_type
        cooldown_minutes = rule.cooldown_minutes or self._config.idle.cooldown_minutes
        # Expire abandoned in_progress after one cooldown window (min 60m).
        in_progress_timeout = max(60, cooldown_minutes)
        if state.is_task_in_progress(cooldown_key, timeout_minutes=in_progress_timeout):
            return SuppressReason.IN_PROGRESS

        if state.is_in_cooldown(cooldown_minutes, key=cooldown_key):
            # Preferred window beats cooldown: once a new window opens (e.g. midnight
            # for hours 0–5), allow the nudge even if the daily cooldown has not
            # elapsed. Cooldown still blocks fast retries *inside* the same window.
            if not self._new_preferred_window_overrides_cooldown(
                state, rule, cooldown_key, now=now
            ):
                return SuppressReason.COOLDOWN

        budget = self._config.idle.nudge_budget_per_hour
        # Inbox reports are work product, not proactive interruptions — never budget-cap them.
        if (
            budget > 0
            and event.event_type not in ("inbox_notify", "inbox_item")
            and state.nudge_count_window(3600) >= budget
        ):
            return SuppressReason.NUDGE_BUDGET

        if rule.preferred_window is not None:
            force_asap = bool(event.metadata.get(FORCE_ASAP_META))
            defer, _prefer_until = should_defer_for_preferred_window(
                rule.preferred_window,
                now,
                force_asap=force_asap,
            )
            if defer:
                return SuppressReason.DEFER_PREFERRED_WINDOW

        return None

    @staticmethod
    def _new_preferred_window_overrides_cooldown(
        state: StateManager,
        rule: RouteRule,
        cooldown_key: str,
        *,
        now: Optional[datetime] = None,
    ) -> bool:
        """True when we are inside preferred hours and last fire was before this window."""
        if rule.preferred_window is None:
            return False
        current = now or datetime.now()
        bounds = window_bounds_containing(current, rule.preferred_window.hours)
        if bounds is None:
            return False
        window_start, _window_end = bounds
        last = state.cooldown_timestamp(cooldown_key)
        if last is None:
            return False
        if float(last) < window_start.timestamp():
            logger.info(
                "Cooldown %s: preferred window started %.0f — ignoring prior cooldown",
                cooldown_key,
                window_start.timestamp(),
            )
            return True
        return False

    @staticmethod
    def blocks_publish(reason: Optional[SuppressReason]) -> bool:
        """True when sources should not publish (defer still publishes for parking)."""
        return reason is not None and reason is not SuppressReason.DEFER_PREFERRED_WINDOW

    def should_notify(
        self,
        state: StateManager,
        event: Event,
        *,
        poll_item_key: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> bool:
        """Return True when the event should be published (deliver now or defer)."""
        return not self.blocks_publish(
            self.check(state, event, poll_item_key=poll_item_key, now=now),
        )

    def prefer_until_ts(
        self,
        event: Event,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        """prefer_until timestamp when the event should wait for a preferred window."""
        rule = self.resolve_rule(event, now=now)
        if rule is None or rule.preferred_window is None:
            return None
        force_asap = bool(event.metadata.get(FORCE_ASAP_META))
        defer, prefer_until = should_defer_for_preferred_window(
            rule.preferred_window,
            now,
            force_asap=force_asap,
        )
        return prefer_until if defer else None

    def log_suppressed(
        self,
        event: Event,
        reason: SuppressReason,
        *,
        poll_item_key: Optional[str] = None,
        source: str = "",
    ) -> None:
        """Emit a debug log for a suppressed or deferred event."""
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
        elif reason is SuppressReason.NUDGE_BUDGET:
            fname = (event.metadata or {}).get("file") or event.cooldown_key or "?"
            logger.warning(
                "%sevent type=%s suppressed — nudge budget exceeded (file=%s id=%s)",
                prefix,
                event.event_type,
                fname,
                event.id,
            )
        elif reason is SuppressReason.DEFER_PREFERRED_WINDOW:
            logger.debug(
                "%sevent type=%s deferred — preferred window (%s)",
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
        if self.blocks_publish(reason):
            assert reason is not None
            self.log_suppressed(probe, reason, source=f"http_poll {entry_point.id}")
            return False
        return True

    def resolve_rule(
        self,
        event: Event,
        *,
        now: Optional[datetime] = None,
    ) -> Optional[RouteRule]:
        """Return the routing rule for an event, if any."""
        return select_rule(
            self._rules,
            event.event_type,
            event.priority,
            event.entry_point,
            now=now,
            task_id=event.task_id,
        )

    def cooldown_key(self, event: Event) -> str:
        """Effective cooldown key for an event."""
        return event.cooldown_key or event.event_type

    def cooldown_minutes(self, rule: RouteRule) -> int:
        """Effective cooldown minutes for a rule."""
        return rule.cooldown_minutes or self._config.idle.cooldown_minutes
