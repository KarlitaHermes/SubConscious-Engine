"""Generic vault file checks — base for rules.md and inbox (future sources).

Vault rules and inbox policy are both: watch paths, read files, match patterns,
emit events. This module holds shared scanning helpers; dedicated sources will
call these and publish to the event bus.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Iterable

logger = logging.getLogger(__name__)


def scan_markdown_lines(
    path: Path,
    predicate: Callable[[str], bool],
    *,
    max_lines: int = 500,
) -> list[str]:
    """Return lines from a markdown file that match ``predicate``."""
    if not path.is_file():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Could not read %s: %s", path, exc)
        return []
    matches: list[str] = []
    for line in content.splitlines()[:max_lines]:
        stripped = line.strip()
        if stripped and predicate(stripped):
            matches.append(stripped)
    return matches


def list_files_newer_than(
    directory: Path,
    since_timestamp: float,
    *,
    suffix: str = ".md",
) -> Iterable[Path]:
    """Yield files in ``directory`` modified after ``since_timestamp``."""
    if not directory.is_dir():
        return
    for path in sorted(directory.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file() and path.suffix == suffix and path.stat().st_mtime > since_timestamp:
            yield path
