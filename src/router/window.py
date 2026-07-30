"""Preferred delivery windows — wait if soon, else ASAP."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional


DEFAULT_MAX_WAIT_HOURS = 12
DEFAULT_FALLBACK = "asap"
FORCE_ASAP_META = "force_asap"


@dataclass(frozen=True)
class PreferredWindow:
    """Soft schedule: prefer these hours, otherwise deliver ASAP."""

    hours: tuple[int, ...]
    max_wait_hours: float = DEFAULT_MAX_WAIT_HOURS
    fallback: str = DEFAULT_FALLBACK

    @classmethod
    def from_raw(cls, raw: Any) -> Optional[PreferredWindow]:
        """Parse preferred_window from config YAML."""
        if not raw or not isinstance(raw, dict):
            return None
        hours_raw = raw.get("hours") or []
        hours = tuple(sorted({int(h) for h in hours_raw if 0 <= int(h) <= 23}))
        if not hours:
            return None
        return cls(
            hours=hours,
            max_wait_hours=float(raw.get("max_wait_hours", DEFAULT_MAX_WAIT_HOURS)),
            fallback=str(raw.get("fallback", DEFAULT_FALLBACK)).lower(),
        )


def window_bounds_containing(now: datetime, hours: tuple[int, ...]) -> Optional[tuple[datetime, datetime]]:
    """Return [start, end) for the contiguous hour run containing *now*, if any."""
    if now.hour not in hours:
        return None
    start = now.replace(minute=0, second=0, microsecond=0)
    while True:
        prev = start - timedelta(hours=1)
        if prev.hour not in hours:
            break
        start = prev
    end = start + timedelta(hours=1)
    while end.hour in hours:
        end += timedelta(hours=1)
    return start, end


def next_preferred_window(
    now: datetime,
    hours: tuple[int, ...],
) -> Optional[tuple[datetime, datetime]]:
    """Next (or current) contiguous preferred window [start, end)."""
    current = window_bounds_containing(now, hours)
    if current is not None:
        return current

    # Search hour-by-hour for the next hour in the set (up to 8 days).
    cursor = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    for _ in range(24 * 8):
        if cursor.hour in hours:
            return window_bounds_containing(cursor, hours)
        cursor += timedelta(hours=1)
    return None


def should_defer_for_preferred_window(
    window: PreferredWindow,
    now: Optional[datetime] = None,
    *,
    force_asap: bool = False,
) -> tuple[bool, Optional[float]]:
    """Return (defer?, prefer_until_ts).

    Defer when the next preferred window starts within max_wait_hours.
    If already inside the window, or wait is too long, or force_asap: do not defer (ASAP).
    """
    # v1: only "asap" fallback. Anything else (or force) → deliver now.
    if force_asap or window.fallback != DEFAULT_FALLBACK:
        return False, None

    current = now or datetime.now()
    if current.hour in window.hours:
        return False, None

    bounds = next_preferred_window(current, window.hours)
    if bounds is None:
        return False, None

    start, end = bounds
    wait_hours = (start - current).total_seconds() / 3600.0
    if wait_hours <= 0:
        return False, None
    if wait_hours > window.max_wait_hours:
        return False, None

    return True, end.timestamp()
