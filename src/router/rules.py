"""Routing rules loaded from configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.router.window import PreferredWindow


@dataclass
class RouteRule:
    """Maps event types to delivery behaviour."""

    event_type: str
    entry_point: Optional[str] = None
    task_id: Optional[str] = None
    target_sources: list[str] = field(default_factory=list)
    broadcast: bool = False
    max_targets: int = 1
    cooldown_minutes: Optional[int] = None
    priority: int = 0
    min_event_priority: int = 0
    active_hours: list[int] = field(default_factory=list)
    active_days: list[int] = field(default_factory=list)
    preferred_window: Optional[PreferredWindow] = None
    # Pin inject to a sticky Hermes session (Karla-Worker SE orchestrator).
    preferred_session_id: Optional[str] = None
    # Optional alternate adapter base URL (Worker gateway subconscious port).
    inject_url: Optional[str] = None
    # telegram (default) | script — script runs deliver.script instead of inject
    mode: str = "telegram"
    script: Optional[str] = None
    # After a successful Worker inject, also drop a notify file in COMMS/Inbox
    # so Face gets inbox_notify even when the cheap lane won't tool-write.
    inbox_report: bool = False

    def is_active_now(self, now: Optional[datetime] = None) -> bool:
        """Return True if the rule is within its configured hard time gate."""
        current = now or datetime.now()
        if self.active_days and current.weekday() not in self.active_days:
            return False
        if self.active_hours and current.hour not in self.active_hours:
            return False
        return True

    def accepts_event_priority(self, event_priority: int) -> bool:
        """Return True if the event meets the rule's minimum priority."""
        return event_priority >= self.min_event_priority


def _rule_task_id(item: dict[str, Any]) -> Optional[str]:
    """Accept match.task_id or match.task (string); empty → None."""
    raw = item.get("task_id", item.get("task"))
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def parse_rules(raw: list[dict[str, Any]]) -> list[RouteRule]:
    """Parse routing rules from config YAML."""
    rules: list[RouteRule] = []
    for item in raw:
        rules.append(
            RouteRule(
                event_type=str(item.get("event_type", item.get("type", "*"))),
                entry_point=item.get("entry_point"),
                task_id=_rule_task_id(item),
                target_sources=list(item.get("target_sources") or []),
                broadcast=bool(item.get("broadcast", False)),
                max_targets=int(item.get("max_targets", 1)),
                cooldown_minutes=item.get("cooldown_minutes"),
                priority=int(item.get("priority", 0)),
                min_event_priority=int(item.get("min_event_priority", 0)),
                active_hours=[int(h) for h in (item.get("active_hours") or [])],
                active_days=[int(d) for d in (item.get("active_days") or [])],
                preferred_window=PreferredWindow.from_raw(item.get("preferred_window")),
                preferred_session_id=(
                    str(item["preferred_session_id"]).strip()
                    if item.get("preferred_session_id")
                    else None
                ),
                inject_url=(
                    str(item["inject_url"]).rstrip("/")
                    if item.get("inject_url")
                    else None
                ),
                mode=str(item.get("mode") or "telegram").strip().lower() or "telegram",
                script=(
                    str(item["script"]).strip()
                    if item.get("script")
                    else None
                ),
                inbox_report=bool(item.get("inbox_report", False)),
            )
        )
    return rules


def match_rule(
    rules: list[RouteRule],
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
    task_id: Optional[str] = None,
) -> RouteRule:
    """Find the best matching rule for an event type and context."""
    selected = select_rule(
        rules, event_type, event_priority, entry_point, now, task_id=task_id,
    )
    if selected is not None:
        return selected
    return RouteRule(event_type=event_type)


def select_rule(
    rules: list[RouteRule],
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
    task_id: Optional[str] = None,
) -> Optional[RouteRule]:
    """Select the best applicable rule.

    Preference order (high → low): exact event_type over ``*``, task-specific
    rule over a generic (no task_id) rule, then rule priority. A rule with
    ``task_id`` only matches events carrying that same id.
    """
    event_task = (str(task_id).strip() if task_id is not None else "") or None
    # (type_exact, task_exact, priority, rule)
    candidates: list[tuple[int, int, int, RouteRule]] = []
    for rule in rules:
        if rule.event_type not in (event_type, "*"):
            continue
        if rule.entry_point and rule.entry_point != entry_point:
            continue
        if rule.task_id and rule.task_id != event_task:
            continue
        if not rule.accepts_event_priority(event_priority):
            continue
        if not rule.is_active_now(now):
            continue
        type_exact = 1 if rule.event_type == event_type else 0
        task_exact = 1 if rule.task_id else 0
        candidates.append((type_exact, task_exact, rule.priority, rule))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return candidates[0][3]


def rule_applicable(
    rule: RouteRule,
    event_type: str,
    event_priority: int = 0,
    entry_point: Optional[str] = None,
    now: Optional[datetime] = None,
    task_id: Optional[str] = None,
) -> bool:
    """Return True if a rule applies to the given event context."""
    event_task = (str(task_id).strip() if task_id is not None else "") or None
    if rule.event_type not in (event_type, "*"):
        return False
    if rule.entry_point and rule.entry_point != entry_point:
        return False
    if rule.task_id and rule.task_id != event_task:
        return False
    if not rule.accepts_event_priority(event_priority):
        return False
    return rule.is_active_now(now)
