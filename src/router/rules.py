"""Routing rules loaded from configuration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class RouteRule:
    """Maps event types to delivery behaviour."""

    event_type: str
    entry_point: Optional[str] = None
    target_sources: list[str] = field(default_factory=list)
    broadcast: bool = False
    max_targets: int = 1
    cooldown_minutes: Optional[int] = None
    priority: int = 0
    min_event_priority: int = 0
    active_hours: list[int] = field(default_factory=list)
    active_days: list[int] = field(default_factory=list)

    def is_active_now(self, now: Optional[datetime] = None) -> bool:
        """Return True if the rule is within its configured time window."""
        current = now or datetime.now()
        if self.active_days and current.weekday() not in self.active_days:
            return False
        if self.active_hours and current.hour not in self.active_hours:
            return False
        return True

    def accepts_event_priority(self, event_priority: int) -> bool:
        """Return True if the event meets the rule's minimum priority."""
        return event_priority >= self.min_event_priority


def parse_rules(raw: list[dict[str, Any]]) -> list[RouteRule]:
    """Parse routing rules from config YAML."""
    rules: list[RouteRule] = []
    for item in raw:
        rules.append(
            RouteRule(
                event_type=str(item.get("event_type", item.get("type", "*"))),
                entry_point=item.get("entry_point"),
                target_sources=list(item.get("target_sources") or []),
                broadcast=bool(item.get("broadcast", False)),
                max_targets=int(item.get("max_targets", 1)),
                cooldown_minutes=item.get("cooldown_minutes"),
                priority=int(item.get("priority", 0)),
                min_event_priority=int(item.get("min_event_priority", 0)),
                active_hours=[int(h) for h in (item.get("active_hours") or [])],
                active_days=[int(d) for d in (item.get("active_days") or [])],
            )
        )
    return rules


def match_rule(
    rules: list[RouteRule],
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
) -> RouteRule:
    """Find the best matching rule for an event type and context."""
    selected = select_rule(rules, event_type, event_priority, entry_point, now)
    if selected is not None:
        return selected
    return RouteRule(event_type=event_type)


def select_rule(
    rules: list[RouteRule],
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[RouteRule]:
    """Select the highest-priority applicable rule, preferring exact type matches."""
    candidates: list[tuple[int, int, RouteRule]] = []
    for rule in rules:
        if rule.event_type not in (event_type, "*"):
            continue
        if rule.entry_point and rule.entry_point != entry_point:
            continue
        if not rule.accepts_event_priority(event_priority):
            continue
        if not rule.is_active_now(now):
            continue
        exactness = 1 if rule.event_type == event_type else 0
        candidates.append((rule.priority, exactness, rule))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def rule_applicable(
    rule: RouteRule,
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Return True if a rule applies to the given event context."""
    if rule.event_type not in (event_type, "*"):
        return False
    if rule.entry_point and rule.entry_point != entry_point:
        return False
    if not rule.accepts_event_priority(event_priority):
        return False
    return rule.is_active_now(now)
