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
