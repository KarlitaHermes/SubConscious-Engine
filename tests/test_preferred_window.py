"""Tests for preferred delivery window helpers."""

from __future__ import annotations

from datetime import datetime

from src.router.window import (
    PreferredWindow,
    next_preferred_window,
    should_defer_for_preferred_window,
    window_bounds_containing,
)


def test_parse_preferred_window() -> None:
    win = PreferredWindow.from_raw({"hours": [0, 1, 2], "max_wait_hours": 12})
    assert win is not None
    assert win.hours == (0, 1, 2)
    assert win.max_wait_hours == 12.0
    assert PreferredWindow.from_raw({}) is None
    assert PreferredWindow.from_raw(None) is None


def test_window_bounds_overnight() -> None:
    now = datetime(2026, 7, 30, 1, 15, 0)
    bounds = window_bounds_containing(now, (0, 1, 2))
    assert bounds is not None
    start, end = bounds
    assert start == datetime(2026, 7, 30, 0, 0, 0)
    assert end == datetime(2026, 7, 30, 3, 0, 0)


def test_next_window_from_afternoon() -> None:
    now = datetime(2026, 7, 30, 14, 0, 0)
    start, end = next_preferred_window(now, (0, 1, 2))  # type: ignore[misc]
    assert start == datetime(2026, 7, 31, 0, 0, 0)
    assert end == datetime(2026, 7, 31, 3, 0, 0)


def test_defer_afternoon_within_max_wait() -> None:
    win = PreferredWindow(hours=(0, 1, 2), max_wait_hours=12)
    now = datetime(2026, 7, 30, 14, 0, 0)
    defer, prefer_until = should_defer_for_preferred_window(win, now)
    assert defer is True
    assert prefer_until == datetime(2026, 7, 31, 3, 0, 0).timestamp()


def test_asap_when_wait_exceeds_max() -> None:
    win = PreferredWindow(hours=(0, 1, 2), max_wait_hours=12)
    now = datetime(2026, 7, 30, 4, 0, 0)  # ~20h until next midnight
    defer, prefer_until = should_defer_for_preferred_window(win, now)
    assert defer is False
    assert prefer_until is None


def test_no_defer_inside_window() -> None:
    win = PreferredWindow(hours=(0, 1, 2), max_wait_hours=12)
    now = datetime(2026, 7, 30, 1, 0, 0)
    defer, prefer_until = should_defer_for_preferred_window(win, now)
    assert defer is False
    assert prefer_until is None


def test_force_asap_skips_defer() -> None:
    win = PreferredWindow(hours=(0, 1, 2), max_wait_hours=12)
    now = datetime(2026, 7, 30, 14, 0, 0)
    defer, _ = should_defer_for_preferred_window(win, now, force_asap=True)
    assert defer is False
