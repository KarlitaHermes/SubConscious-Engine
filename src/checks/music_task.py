"""Detect when daily music curation is due (for idle task_id tagging)."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

MUSIC_TASK_ID = "music_curation"
_MUSIC_LINE = re.compile(
    r"daily music curation.*?Last done:\W*([0-9]{4}-[0-9]{2}-[0-9]{2}|never)",
    re.IGNORECASE | re.DOTALL,
)
_DONE_FLAG = Path.home() / ".hermes" / ".daily_music_done"


def music_curation_due(
    vault_root: Path,
    *,
    now: Optional[datetime] = None,
) -> bool:
    """True when daily music curation has not been completed for local today."""
    today = (now or datetime.now()).strftime("%Y-%m-%d")
    if _DONE_FLAG.exists():
        try:
            if json.loads(_DONE_FLAG.read_text()).get("last_done") == today:
                return False
        except Exception:
            pass

    tasks = vault_root / "Projects" / "Maintenance" / "tasks.md"
    if not tasks.is_file():
        return False
    try:
        text = tasks.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    match = _MUSIC_LINE.search(text)
    if not match:
        return False
    last = match.group(1).strip().lower()
    return last != today


def resolve_maintenance_task_id(
    vault_root: Path,
    *,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Return music_curation when that task is due; otherwise None (generic maintenance)."""
    if music_curation_due(vault_root, now=now):
        return MUSIC_TASK_ID
    return None
