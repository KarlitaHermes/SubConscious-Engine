"""Runtime context for vault rule evaluation."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


def build_vault_context(
    vault_root: Path,
    *,
    inbox_dir: Path | None = None,
    last_nudge_timestamp: float = 0.0,
) -> dict[str, Any]:
    """Gather filesystem metrics used by rules.md conditions."""
    ctx: dict[str, Any] = {
        "signal_log_size_kb": 0,
        "signal_log_lines": 0,
        "report_count": 0,
        "memory_size_chars": 0,
        "config_version_mismatch": False,
        "uptime_hours": 0,
        "oldest_inbox_days": 0,
        "idle_minutes": 0,
        "last_nudge_minutes": 999,
    }

    signal_log = vault_root / "COMMS" / "signal-log.md"
    if signal_log.is_file():
        try:
            content = signal_log.read_text(encoding="utf-8", errors="replace")
            ctx["signal_log_size_kb"] = max(1, len(content.encode("utf-8")) // 1024)
            ctx["signal_log_lines"] = len(content.splitlines())
        except OSError:
            pass

    reports_dir = vault_root / "Projects" / "ORCHESTRATOR" / "Reports"
    if reports_dir.is_dir():
        try:
            ctx["report_count"] = sum(
                1 for name in os.listdir(reports_dir) if name.endswith(".md")
            )
        except OSError:
            pass

    memory_path = vault_root / "memory.md"
    if memory_path.is_file():
        try:
            ctx["memory_size_chars"] = len(memory_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass

    scan_inbox = inbox_dir or (vault_root / "COMMS" / "Inbox")
    if scan_inbox.is_dir():
        now = time.time()
        oldest_age_days = 0.0
        try:
            for name in os.listdir(scan_inbox):
                path = scan_inbox / name
                if not path.is_file() or path.suffix != ".md":
                    continue
                age_days = (now - path.stat().st_mtime) / 86400
                oldest_age_days = max(oldest_age_days, age_days)
        except OSError:
            pass
        ctx["oldest_inbox_days"] = int(oldest_age_days)

    if last_nudge_timestamp > 0:
        ctx["last_nudge_minutes"] = int((time.time() - last_nudge_timestamp) / 60)

    return ctx
