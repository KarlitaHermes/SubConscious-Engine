"""Scan vault files for pending decision items."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DECISION_MARKERS = (
    "⚠️",
    "needs decision",
    "Rev to decide",
    "for Rev:",
    "should we",
    "ACTION REQUIRED",
)


def get_pending_decisions(vault_root: Path, since_timestamp: float = 0.0) -> list[str]:
    """Return short summaries of items needing Rev's decision.

    Scans recent ORCHESTRATOR reports and the DREAM backlog for markers.
    Only includes files modified after ``since_timestamp``.
    """
    decisions: list[str] = []
    reports_dir = vault_root / "Projects" / "ORCHESTRATOR" / "Reports"
    dream_backlog = vault_root / "Projects" / "Dream-Journal" / "Backlog.md"

    if reports_dir.exists():
        now = time.time()
        for name in sorted(os.listdir(reports_dir), reverse=True):
            path = reports_dir / name
            if not path.is_file() or path.suffix != ".md":
                continue
            if now - path.stat().st_mtime > 86400:
                break
            if path.stat().st_mtime <= since_timestamp:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                logger.debug("Could not read report %s: %s", path, exc)
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if any(marker in stripped for marker in DECISION_MARKERS):
                    decisions.append(f"  • [{name}] {stripped[:120]}")

    if dream_backlog.exists():
        try:
            if dream_backlog.stat().st_mtime > since_timestamp:
                content = dream_backlog.read_text(encoding="utf-8", errors="replace")
                new_items = [ln.strip() for ln in content.splitlines() if ln.strip().startswith("- [ ]")]
                if new_items:
                    decisions.append(
                        f"  • [Dream Backlog] {len(new_items)} new item(s) awaiting action",
                    )
        except OSError as exc:
            logger.debug("Could not read dream backlog: %s", exc)

    return decisions[:10]
