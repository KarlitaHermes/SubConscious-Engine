"""Event data models for the router."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class EventSourceKind(str, Enum):
    """Origin of an inbound event."""

    FILE = "file"
    REST = "rest"
    IDLE = "idle"


@dataclass
class Event:
    """Inbound event to be routed and delivered.

    Target session(s) are resolved by the router from rules, timing, and
    optional hints — explicit targets are not required.
    """

    text: str
    event_type: str
    source: EventSourceKind
    entry_point: Optional[str] = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    preferred_target: Optional[str] = None
    preferred_source: Optional[str] = None
    targets: list[str] = field(default_factory=list)
    priority: int = 0
    cooldown_key: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: EventSourceKind) -> Event:
        """Build an event from a JSON/YAML payload."""
        return cls(
            text=str(data.get("text", "")),
            event_type=str(data.get("event_type", data.get("type", "custom"))),
            source=source,
            entry_point=data.get("entry_point"),
            id=str(data.get("id", uuid.uuid4().hex)),
            preferred_target=data.get("preferred_target"),
            preferred_source=data.get("preferred_source"),
            targets=list(data.get("targets") or []),
            priority=int(data.get("priority", 0)),
            cooldown_key=data.get("cooldown_key"),
            metadata=dict(data.get("metadata") or {}),
            created_at=float(data.get("created_at", time.time())),
        )


@dataclass
class DeliveryResult:
    """Outcome of delivering an event to one session."""

    session_id: str
    success: bool
    error: Optional[str] = None
