"""Tests for routing rules."""

from datetime import datetime

import pytest

from src.router.rules import RouteRule, match_rule, parse_rules, rule_applicable, select_rule


def test_parse_rules_full() -> None:
    raw = [
        {
            "event_type": "maintenance",
            "target_sources": ["telegram"],
            "broadcast": False,
            "max_targets": 1,
            "cooldown_minutes": 60,
            "priority": 10,
            "min_event_priority": 5,
            "active_hours": [9, 10, 11],
            "active_days": [0, 1, 2, 3, 4],
        },
    ]
    rules = parse_rules(raw)
    assert rules[0].priority == 10
    assert rules[0].min_event_priority == 5
    assert rules[0].active_hours == [9, 10, 11]
    assert rules[0].active_days == [0, 1, 2, 3, 4]


def test_parse_rules_type_alias() -> None:
    rules = parse_rules([{"type": "alert", "target_sources": ["telegram"]}])
    assert rules[0].event_type == "alert"


def test_parse_rules_defaults() -> None:
    rules = parse_rules([{}])
    assert rules[0].event_type == "*"
    assert rules[0].priority == 0
    assert rules[0].active_hours == []


def test_match_rule_exact() -> None:
    rules = [
        RouteRule(event_type="maintenance", target_sources=["telegram"], priority=10),
        RouteRule(event_type="*", target_sources=["cli"], priority=1),
    ]
    matched = match_rule(rules, "maintenance")
    assert matched.event_type == "maintenance"


def test_match_rule_wildcard() -> None:
    rules = [
        RouteRule(event_type="maintenance", target_sources=["telegram"]),
        RouteRule(event_type="*", target_sources=["cli"]),
    ]
    matched = match_rule(rules, "unknown_type")
    assert matched.event_type == "*"


def test_match_rule_fallback_default() -> None:
    matched = match_rule([], "orphan")
    assert matched.event_type == "orphan"


def test_select_rule_prefers_higher_priority() -> None:
    rules = [
        RouteRule(event_type="custom", target_sources=["telegram"], priority=1),
        RouteRule(event_type="custom", target_sources=["telegram"], priority=99),
    ]
    selected = select_rule(rules, "custom", event_priority=0)
    assert selected is not None
    assert selected.priority == 99


def test_select_rule_exact_beats_wildcard_at_same_priority() -> None:
    rules = [
        RouteRule(event_type="*", target_sources=["telegram"], priority=10),
        RouteRule(event_type="custom", target_sources=["telegram"], priority=10),
    ]
    selected = select_rule(rules, "custom", event_priority=0)
    assert selected is not None
    assert selected.event_type == "custom"


def test_select_rule_min_event_priority() -> None:
    rules = [
        RouteRule(
            event_type="alert",
            target_sources=["telegram"],
            min_event_priority=20,
        ),
    ]
    assert select_rule(rules, "alert", event_priority=5) is None
    assert select_rule(rules, "alert", event_priority=20) is not None


def test_rule_active_hours() -> None:
    rule = RouteRule(event_type="x", active_hours=[10, 11, 12])
    assert rule.is_active_now(datetime(2026, 6, 15, 11, 30)) is True
    assert rule.is_active_now(datetime(2026, 6, 15, 23, 0)) is False


def test_rule_active_days() -> None:
    rule = RouteRule(event_type="x", active_days=[0])  # Monday
    monday = datetime(2026, 6, 15, 12, 0)  # Sunday actually - 2026-06-15 is Monday? Let me check: June 15 2026 is Monday (weekday 0)
    assert monday.weekday() == 0
    assert rule.is_active_now(monday) is True
    assert rule.is_active_now(datetime(2026, 6, 16, 12, 0)) is False


def test_select_rule_entry_point_filter() -> None:
    rules = [
        RouteRule(
            event_type="custom",
            entry_point="api",
            target_sources=["telegram"],
            priority=10,
        ),
        RouteRule(
            event_type="custom",
            target_sources=["cli"],
            priority=1,
        ),
    ]
    assert select_rule(rules, "custom", entry_point="api").target_sources == ["telegram"]
    assert select_rule(rules, "custom", entry_point="events_drop").target_sources == ["cli"]


def test_rule_applicable_combined() -> None:
    rule = RouteRule(
        event_type="alert",
        min_event_priority=10,
        active_hours=[12],
        active_days=[0],
    )
    assert rule_applicable(rule, "alert", 10, now=datetime(2026, 6, 15, 12, 0)) is True
    assert rule_applicable(rule, "alert", 5, now=datetime(2026, 6, 15, 12, 0)) is False
    assert rule_applicable(rule, "other", 10, now=datetime(2026, 6, 15, 12, 0)) is False
