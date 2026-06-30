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

    def is_task_in_progress(self, cooldown_key: str) -> bool:
        """Return True if Hermes reported this cooldown_key as in progress."""
        tasks = self._data.get("tasks_in_progress", {})
        return cooldown_key in tasks

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

