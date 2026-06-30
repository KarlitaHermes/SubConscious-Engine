"""System rules engine — load rules.md and evaluate conditions."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FREQUENCY_COOLDOWN_MINUTES = {
    "every 30 min": 30,
    "every 48h": 48 * 60,
    "weekly": 7 * 24 * 60,
    "once per day": 24 * 60,
}


@dataclass
class VaultRuleMatch:
    """A matched rule ready to become an event."""

    rule_id: str
    description: str
    priority: str
    action_type: str
    prompt: str
    event_priority: int = 5


def resolve_rules_path(path: Path) -> Path:
    """Resolve vault root or direct rules.md path."""
    if path.is_file():
        return path
    return path / "Projects" / "Maintenance" / "rules.md"


class VaultRulesEngine:
    """Load and evaluate system rules from rules.md."""

    def __init__(self, rules_path: Path) -> None:
        self._rules_path = rules_path
        self._rules: list[dict[str, Any]] = []
        self._last_loaded_mtime = 0.0
        self.reload_if_changed()

    def reload_if_changed(self) -> None:
        """Reload rules when the file changes."""
        if not self._rules_path.is_file():
            self._rules = []
            return
        mtime = self._rules_path.stat().st_mtime
        if mtime <= self._last_loaded_mtime and self._rules:
            return
        self._rules = self._load_rules()
        self._last_loaded_mtime = mtime

    def _load_rules(self) -> list[dict[str, Any]]:
        if not self._rules_path.is_file():
            logger.warning("rules.md not found at %s", self._rules_path)
            return []

        content = self._rules_path.read_text(encoding="utf-8", errors="replace")
        if content.startswith("---"):
            _, _, body = content.split("---", 2)
        else:
            body = content

        rules: list[dict[str, Any]] = []
        current_rule: dict[str, Any] | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("## Rule "):
                if current_rule:
                    rules.append(current_rule)
                rule_name = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
                current_rule = {
                    "name": rule_name,
                    "condition": "",
                    "action": "",
                    "priority": "LOW",
                    "enabled": True,
                    "frequency": None,
                }
            elif current_rule is not None:
                if stripped.startswith("**Condition:**"):
                    current_rule["condition"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("**Action:**"):
                    current_rule["action"] = stripped.split(":", 1)[1].strip()
                elif stripped.startswith("**Priority:**"):
                    current_rule["priority"] = stripped.split(":", 1)[1].strip().upper()
                elif stripped.startswith("**Frequency:**"):
                    freq = stripped.split(":", 1)[1].strip()
                    current_rule["frequency"] = None if freq.lower() == "never" else freq
                elif stripped.lower() == "enabled: false":
                    current_rule["enabled"] = False

        if current_rule:
            rules.append(current_rule)

        logger.info("Loaded %d rules from %s", len(rules), self._rules_path)
        return rules

    def evaluate(
        self,
        context: dict[str, Any],
        *,
        rule_last_run: dict[str, float] | None = None,
    ) -> list[VaultRuleMatch]:
        """Evaluate enabled rules and return matches not in frequency cooldown."""
        self.reload_if_changed()
        last_run = rule_last_run or {}
        matches: list[VaultRuleMatch] = []

        for rule in self._rules:
            if not rule.get("enabled", True):
                continue

            rule_id = str(rule["name"])
            if not self._evaluate_condition(rule.get("condition", ""), context):
                continue

            if not self._frequency_allows(rule, last_run.get(rule_id)):
                continue

            action_desc = rule.get("action", "")
            matches.append(
                VaultRuleMatch(
                    rule_id=rule_id,
                    description=action_desc,
                    priority=str(rule.get("priority", "LOW")),
                    action_type=self._infer_action_type(action_desc),
                    prompt=self._build_prompt(rule),
                    event_priority=self._priority_to_int(str(rule.get("priority", "LOW"))),
                ),
            )

        return matches

    def _frequency_allows(self, rule: dict[str, Any], last_run: float | None) -> bool:
        frequency = rule.get("frequency")
        if not frequency or last_run is None:
            return True
        cooldown = FREQUENCY_COOLDOWN_MINUTES.get(str(frequency).lower().strip())
        if cooldown is None:
            return True
        return (time.time() - last_run) >= cooldown * 60

    def _evaluate_condition(self, condition: str, ctx: dict[str, Any]) -> bool:
        condition = condition.lower().strip()
        if not condition:
            return False

        if "signal log" in condition and ("kb" in condition or "lines" in condition):
            threshold_kb = self._extract_number(condition, "kb")
            threshold_lines = self._extract_number(condition, "lines")
            if threshold_kb and ctx.get("signal_log_size_kb", 0) > threshold_kb:
                return True
            if threshold_lines and ctx.get("signal_log_lines", 0) > threshold_lines:
                return True
            return False

        if "report" in condition and ">" in condition:
            threshold = self._extract_number(condition, None)
            return bool(threshold and ctx.get("report_count", 0) > threshold)

        if "memory" in condition and ("char" in condition or "kb" in condition):
            threshold = self._extract_number(condition, "char")
            return bool(threshold and ctx.get("memory_size_chars", 0) > threshold)

        if "config" in condition and "mismatch" in condition:
            return bool(ctx.get("config_version_mismatch", False))

        if "uptime" in condition or "running" in condition:
            threshold_hours = self._extract_number(condition, "hour")
            return bool(threshold_hours and ctx.get("uptime_hours", 0) > threshold_hours)

        if "inbox" in condition and "older" in condition:
            threshold_days = self._extract_number(condition, "day")
            return bool(threshold_days and ctx.get("oldest_inbox_days", 0) > threshold_days)

        if "idle" in condition and ("minute" in condition or "min" in condition):
            threshold_min = self._extract_number(condition, "min")
            idle_min = ctx.get("idle_minutes", 0)
            last_nudge_min = ctx.get("last_nudge_minutes", 999)
            if threshold_min and idle_min > threshold_min:
                return last_nudge_min > 60 or last_nudge_min == 999
            return False

        logger.debug("Unknown condition format: %s", condition)
        return False

    @staticmethod
    def _extract_number(text: str, unit: str | None) -> int | None:
        if unit:
            pattern = rf"(\d+)\s*{unit}"
        else:
            pattern = r">?\s*(\d+)"
        match = re.search(pattern, text)
        return int(match.group(1)) if match else None

    @staticmethod
    def _infer_action_type(action_desc: str) -> str:
        desc = action_desc.lower()
        if "archive" in desc or "truncate" in desc:
            return "archive"
        if "notify" in desc:
            return "notify"
        if "run" in desc or "migrate" in desc:
            return "run_script"
        return "log"

    @staticmethod
    def _priority_to_int(priority: str) -> int:
        return {
            "LOW": 1,
            "MEDIUM": 5,
            "HIGH": 10,
            "URGENT": 20,
        }.get(priority.upper(), 1)

    @staticmethod
    def _build_prompt(rule: dict[str, Any]) -> str:
        name = rule.get("name", "unknown")
        condition = rule.get("condition", "")
        action = rule.get("action", "")
        priority = rule.get("priority", "LOW")
        return (
            f"[SUBCONSCIOUS] Vault rule triggered: {name}\n\n"
            f"Priority: {priority}\n"
            f"Condition: {condition}\n"
            f"Action: {action}\n\n"
            f"Karla: evaluate this system rule and take the configured action. "
            f"Log what you did in the Maintenance reports directory."
        )
