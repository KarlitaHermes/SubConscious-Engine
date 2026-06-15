"""Inbox file classification and prompt building."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

STANDING_FILENAMES = frozenset(
    {
        "dream-task-v2.md",
        "dream-task.md",
        "quick-wins-vault-cleanup.md",
        "researcher-task.md",
        ".processed",
        "inbox.lock",
    },
)

SKIP_PREFIXES = ("dream-task-", "researcher-task-", "quick-wins-")
NOTIFY_PREFIXES = ("news-digest-", "research-digest-", "dream-session-")
EMAIL_PREFIXES = ("email-",)

VAULT_DEST_BY_PREFIX: tuple[tuple[str, str], ...] = (
    ("news-digest-", "Projects/News-Digests"),
    ("dream-session-", "Projects/Dream-Journal"),
    ("research-digest-", "Projects/Research"),
    ("knowledge-graph-", "Technical"),
    ("memory-optimization-", "Technical"),
    ("memory-audit-", "Technical"),
)
DEFAULT_VAULT_DEST = "Projects/Inbox-Processed"


@dataclass
class InboxClassification:
    """How an inbox file should be handled."""

    filename: str
    disposition: str  # skip | notify | delegate | review
    vault_dest: str
    priority: int = 0
    event_type: str = "inbox_item"


def read_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    """Parse optional YAML frontmatter from a markdown file."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.debug("Could not read %s: %s", path, exc)
        return {}, ""

    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    meta = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def is_standing_file(filename: str) -> bool:
    """Return True if the file must never be processed."""
    if filename in STANDING_FILENAMES:
        return True
    return any(filename.startswith(prefix) for prefix in SKIP_PREFIXES)


def vault_dest_relative(filename: str) -> str:
    """Return vault-relative directory for storing inbox content."""
    for prefix, dest in VAULT_DEST_BY_PREFIX:
        if filename.startswith(prefix):
            return dest
    return DEFAULT_VAULT_DEST


def classify_inbox_file(path: Path, *, default_event_type: str = "inbox_item") -> InboxClassification | None:
    """Classify an inbox markdown file. Returns None for standing/skipped files."""
    filename = path.name
    if path.suffix.lower() != ".md":
        return None
    if is_standing_file(filename):
        return None

    metadata, _body = read_frontmatter(path)
    vault_dest = vault_dest_relative(filename)

    priority = 0
    event_type = default_event_type
    if metadata:
        raw_priority = str(metadata.get("priority", "")).strip().lower()
        if raw_priority == "high":
            priority = 10
            event_type = "inbox_notify"

    if any(filename.startswith(prefix) for prefix in NOTIFY_PREFIXES):
        return InboxClassification(
            filename=filename,
            disposition="notify",
            vault_dest=vault_dest,
            priority=max(priority, 10),
            event_type="inbox_notify",
        )

    if any(filename.startswith(prefix) for prefix in EMAIL_PREFIXES):
        return InboxClassification(
            filename=filename,
            disposition="delegate",
            vault_dest=vault_dest,
            priority=priority,
            event_type=default_event_type,
        )

    routine_prefixes = ("memory-", "knowledge-graph-", "inbox-")
    if any(filename.startswith(prefix) for prefix in routine_prefixes):
        return InboxClassification(
            filename=filename,
            disposition="delegate",
            vault_dest=vault_dest,
            priority=priority,
            event_type=default_event_type,
        )

    return InboxClassification(
        filename=filename,
        disposition="review",
        vault_dest=vault_dest,
        priority=priority,
        event_type=default_event_type,
    )


def build_inbox_prompt(path: Path, classification: InboxClassification, vault_root: Path) -> str:
    """Build injection text for a new inbox file."""
    _metadata, body = read_frontmatter(path)
    excerpt = body.strip()
    if len(excerpt) > 2500:
        excerpt = excerpt[:2500] + "\n…"

    dest = vault_root / classification.vault_dest
    return (
        f"[SUBCONSCIOUS] New inbox file: {classification.filename}\n\n"
        f"Disposition: {classification.disposition}\n"
        f"Suggested vault destination: {dest}\n\n"
        f"Karla: review this inbox drop. Classify as notify Rev, file to vault, "
        f"delegate to a sub-agent, or mark as routine. Content:\n\n"
        f"{excerpt or '(empty file)'}"
    )
