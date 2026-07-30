"""Persistent engine state (cooldowns, delivery history)."""

from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

ACK_STATUS_IN_PROGRESS = "in_progress"
ACK_STATUS_DONE = "done"
ACK_TERMINAL_STATUSES = frozenset({ACK_STATUS_DONE, "completed"})
# ponytail: unbounded in_progress after /new or gateway reboot; expire then upgrade to session-bound acks
DEFAULT_IN_PROGRESS_TIMEOUT_MINUTES = 180


class StateManager:
    """Manages engine state persistence."""

    def __init__(self, state_file: Path) -> None:
        self._state_file = state_file
        self._data: dict[str, Any] = {
            "last_trigger": None,
            "trigger_count": 0,
            "idle_trigger_count": 0,
            "idle_period_active": False,
            "last_decisions_nudge": None,
            "last_observed_activity": None,
            "cooldowns": {},
            "deliveries": [],
            "nudge_timestamps": [],
        }
        self.load()

    def load(self) -> None:
        """Load state from YAML file."""
        if not self._state_file.exists():
            return
        try:
            raw = yaml.safe_load(self._state_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._data.update(raw)
        except Exception as exc:
            logger.warning("Failed to load state from %s: %s", self._state_file, exc)

    def save(self) -> None:
        """Save state to YAML file atomically."""
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self._state_file.parent,
                prefix=".state-",
                suffix=".tmp",
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                yaml.safe_dump(self._data, fh, default_flow_style=False)
            os.replace(tmp_path, self._state_file)
        except Exception as exc:
            logger.warning("Failed to save state: %s", exc)

    def is_in_cooldown(self, cooldown_minutes: int, key: str = "default") -> bool:
        """Check if a cooldown key is still active."""
        cooldowns = self._data.setdefault("cooldowns", {})
        last = cooldowns.get(key)
        if last is None:
            return False
        elapsed = time.time() - float(last)
        return elapsed < cooldown_minutes * 60

    def record_delivery(
        self,
        event_id: str,
        event_type: str,
        session_ids: list[str],
        success: bool,
        cooldown_key: str = "default",
    ) -> None:
        """Record a delivery and update cooldowns."""
        now = time.time()
        if success:
            self._data["last_trigger"] = now
            self._data["trigger_count"] = int(self._data.get("trigger_count", 0)) + 1
            cooldowns = self._data.setdefault("cooldowns", {})
            cooldowns[cooldown_key] = now
            # Track for nudge budget
            timestamps = self._data.setdefault("nudge_timestamps", [])
            timestamps.append(now)
            # Keep only last 24h
            cutoff = now - 86400
            self._data["nudge_timestamps"] = [t for t in timestamps if t > cutoff]

        deliveries = self._data.setdefault("deliveries", [])
        deliveries.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "session_ids": session_ids,
                "success": success,
                "timestamp": now,
            }
        )
        if len(deliveries) > 100:
            self._data["deliveries"] = deliveries[-100:]
        self.save()

    def next_idle_event_type(self) -> str:
        """Return maintenance or research for the next idle trigger (odd/even alternation)."""
        next_count = self.idle_trigger_count + 1
        return "maintenance" if next_count % 2 == 1 else "research"

    def record_idle_trigger(self) -> int:
        """Increment idle trigger count when an idle event is published."""
        count = self.idle_trigger_count + 1
        self._data["idle_trigger_count"] = count
        self.save()
        return count

    @property
    def idle_trigger_count(self) -> int:
        return int(self._data.get("idle_trigger_count", 0))

    @property
    def idle_period_active(self) -> bool:
        return bool(self._data.get("idle_period_active", False))

    def set_idle_period_active(self, active: bool) -> None:
        self._data["idle_period_active"] = active
        self.save()

    @property
    def last_observed_activity(self) -> Optional[float]:
        val = self._data.get("last_observed_activity")
        return float(val) if val is not None else None

    def update_observed_activity(self, timestamp: Optional[float]) -> None:
        if timestamp is not None:
            self._data["last_observed_activity"] = timestamp
            self.save()

    @property
    def last_decisions_nudge(self) -> float:
        val = self._data.get("last_decisions_nudge")
        return float(val) if val is not None else 0.0

    def record_decisions_nudge(self) -> None:
        self._data["last_decisions_nudge"] = time.time()
        self._data["idle_period_active"] = False
        self.save()

    @property
    def trigger_count(self) -> int:
        return int(self._data.get("trigger_count", 0))

    @property
    def last_trigger_time(self) -> Optional[float]:
        val = self._data.get("last_trigger")
        return float(val) if val is not None else None

    def is_file_processed(self, entry_point_id: str, filename: str) -> bool:
        """Return True if an inbox/directory file was already emitted."""
        processed = self._data.setdefault("processed_files", {})
        entry = processed.get(entry_point_id, {})
        return filename in entry

    def mark_file_processed(self, entry_point_id: str, filename: str) -> None:
        """Record that a directory file has been published as an event."""
        processed = self._data.setdefault("processed_files", {})
        entry_files = processed.setdefault(entry_point_id, {})
        entry_files[filename] = time.time()
        self.save()

    @property
    def rule_last_run(self) -> dict[str, float]:
        raw = self._data.get("rule_last_run", {})
        if not isinstance(raw, dict):
            return {}
        return {str(key): float(value) for key, value in raw.items()}

    def record_rule_run(self, rule_id: str) -> None:
        """Record when a vault rule last fired."""
        runs = self._data.setdefault("rule_last_run", {})
        runs[rule_id] = time.time()
        self.save()

    def is_poll_item_seen(self, entry_point_id: str, item_key: str) -> bool:
        """Return True if an outbound poll item was already published."""
        seen = self._data.get("poll_seen", {})
        entry = seen.get(entry_point_id, {})
        return item_key in entry

    def mark_poll_item_seen(self, entry_point_id: str, item_key: str) -> None:
        """Record a published outbound poll item for deduplication."""
        seen = self._data.setdefault("poll_seen", {})
        entry_items = seen.setdefault(entry_point_id, {})
        entry_items[item_key] = time.time()
        self.save()

    @property
    def last_agent_handled(self) -> Optional[float]:
        """Timestamp of last agent ack (in_progress or done)."""
        val = self._data.get("last_agent_handled")
        return float(val) if val is not None else None

    def is_task_in_progress(
        self,
        cooldown_key: str,
        *,
        timeout_minutes: int | None = None,
    ) -> bool:
        """Return True if Hermes reported this cooldown_key as in progress.

        Stale entries expire after *timeout_minutes* (default 180) so a killed
        agent after /new or gateway reboot cannot block nudges forever.
        """
        tasks = self._data.get("tasks_in_progress", {})
        entry = tasks.get(cooldown_key)
        if entry is None:
            return False
        timeout = (
            DEFAULT_IN_PROGRESS_TIMEOUT_MINUTES
            if timeout_minutes is None
            else max(1, int(timeout_minutes))
        )
        since = float(entry.get("since") or 0.0)
        if since and (time.time() - since) > timeout * 60:
            tasks.pop(cooldown_key, None)
            self.save()
            logger.info(
                "Cleared stale in_progress for %s (age > %dm)",
                cooldown_key,
                timeout,
            )
            return False
        return True

    def note_active_session(self, source: str, session_id: str) -> bool:
        """Record the live session for *source*. Clear in_progress on change.

        Returns True if the active session id changed (and tasks were cleared).
        """
        if not source or not session_id:
            return False
        active = self._data.setdefault("active_sessions", {})
        previous = active.get(source)
        if previous == session_id:
            return False
        active[source] = session_id
        tasks = self._data.get("tasks_in_progress") or {}
        if previous and tasks:
            logger.info(
                "Active %s session changed %s → %s; clearing %d in_progress task(s)",
                source,
                previous,
                session_id,
                len(tasks),
            )
            self._data["tasks_in_progress"] = {}
        self.save()
        return previous is not None and previous != session_id

    def record_ack(
        self,
        cooldown_key: str,
        cooldown_minutes: int,
        *,
        status: str = ACK_STATUS_DONE,
        reset_idle_period: bool = False,
        event_id: Optional[str] = None,
    ) -> None:
        """Record agent feedback — in_progress counts as activity; done sets cooldown."""
        now = time.time()
        self._data["last_agent_handled"] = now
        normalized = status.strip().lower()

        tasks = self._data.setdefault("tasks_in_progress", {})
        if normalized == ACK_STATUS_IN_PROGRESS:
            tasks[cooldown_key] = {
                "since": now,
                "event_id": event_id,
            }
        elif normalized in ACK_TERMINAL_STATUSES:
            tasks.pop(cooldown_key, None)
            self._data.setdefault("cooldowns", {})[cooldown_key] = now
            if reset_idle_period:
                self._data["idle_period_active"] = False
        else:
            logger.warning("Unknown ack status %r for %s", status, cooldown_key)

        acks = self._data.setdefault("acks", [])
        acks.append(
            {
                "cooldown_key": cooldown_key,
                "status": normalized,
                "event_id": event_id,
                "timestamp": now,
            },
        )
        if len(acks) > 50:
            self._data["acks"] = acks[-50:]
        self.save()
        logger.info("Agent ack %s for cooldown_key=%s", normalized, cooldown_key)

    # ------------------------------------------------------------------
    # Nudge budget: rolling window of nudge timestamps
    # ------------------------------------------------------------------

    def nudge_count_window(self, window_seconds: int = 3600) -> int:
        """Return the number of nudges delivered in the last *window_seconds*."""
        cutoff = time.time() - window_seconds
        timestamps = self._data.get("nudge_timestamps", [])
        # Prune old entries
        recent = [t for t in timestamps if t > cutoff]
        return len(recent)

    def record_nudge_in_window(self) -> None:
        """Record a nudge delivery for budget tracking."""
        now = time.time()
        timestamps = self._data.setdefault("nudge_timestamps", [])
        timestamps.append(now)
        # Keep only last 24h of timestamps to avoid unbounded growth
        cutoff = now - 86400
        self._data["nudge_timestamps"] = [t for t in timestamps if t > cutoff]
        self.save()

    # ------------------------------------------------------------------
    # Recent deliveries: context for prompt enrichment
    # ------------------------------------------------------------------

    def recent_deliveries(self, limit: int = 5) -> list[tuple[str, float]]:
        """Return the last *limit* deliveries as (event_type, minutes_ago) tuples."""
        deliveries = self._data.get("deliveries", [])
        now = time.time()
        result: list[tuple[str, float]] = []
        for d in reversed(deliveries[-limit:]):
            ts = d.get("timestamp", 0)
            minutes_ago = max(0.0, (now - ts) / 60) if ts else 0.0
            result.append((d.get("event_type", "unknown"), minutes_ago))
        return result

    # ------------------------------------------------------------------
    # Deferred queue: preferred window → hold, else ASAP after prefer_until
    # ------------------------------------------------------------------

    def park_deferred(
        self,
        cooldown_key: str,
        *,
        event_type: str,
        text: str,
        source: str,
        entry_point: Optional[str],
        priority: int,
        preferred_target: Optional[str],
        preferred_source: Optional[str],
        prefer_until: float,
        preferred_hours: list[int],
        metadata: Optional[dict[str, Any]] = None,
        event_id: Optional[str] = None,
    ) -> None:
        """Park an event until preferred window opens or prefer_until (ASAP)."""
        deferred = self._data.setdefault("deferred", {})
        deferred[cooldown_key] = {
            "event_id": event_id,
            "event_type": event_type,
            "text": text,
            "source": source,
            "entry_point": entry_point,
            "priority": priority,
            "preferred_target": preferred_target,
            "preferred_source": preferred_source,
            "cooldown_key": cooldown_key,
            "prefer_until": float(prefer_until),
            "preferred_hours": list(preferred_hours),
            "metadata": dict(metadata or {}),
            "created_at": time.time(),
        }
        self.save()
        logger.info(
            "Parked deferred %s until prefer_until=%.0f (hours=%s)",
            cooldown_key,
            prefer_until,
            preferred_hours,
        )

    def clear_deferred(self, cooldown_key: str) -> None:
        """Remove a parked deferred event."""
        deferred = self._data.get("deferred") or {}
        if cooldown_key in deferred:
            deferred.pop(cooldown_key, None)
            self.save()

    def get_deferred(self, cooldown_key: str) -> Optional[dict[str, Any]]:
        """Return one deferred entry, if present."""
        deferred = self._data.get("deferred") or {}
        entry = deferred.get(cooldown_key)
        return dict(entry) if isinstance(entry, dict) else None

    def due_deferred(self, now: Optional[float] = None) -> list[dict[str, Any]]:
        """Entries ready to promote: inside preferred hours or past prefer_until."""
        from datetime import datetime

        current_ts = time.time() if now is None else float(now)
        current = datetime.fromtimestamp(current_ts)
        deferred = self._data.get("deferred") or {}
        due: list[dict[str, Any]] = []
        for key, entry in list(deferred.items()):
            if not isinstance(entry, dict):
                continue
            hours = [int(h) for h in (entry.get("preferred_hours") or [])]
            prefer_until = float(entry.get("prefer_until") or 0.0)
            in_window = current.hour in hours if hours else False
            expired = prefer_until > 0 and current_ts >= prefer_until
            if in_window or expired:
                item = dict(entry)
                item["cooldown_key"] = key
                item["force_asap"] = bool(expired and not in_window)
                due.append(item)
        return due

