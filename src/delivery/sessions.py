"""Session registry backed by the SubConscious Adapter."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

SKIP_SOURCES = frozenset({"cron", "subagent", "api_server"})


@dataclass
class SessionInfo:
    """Active session from the adapter."""

    id: str
    source: str
    user_id: Optional[str]
    title: Optional[str]
    started_at: float
    message_count: int
    active: bool = False


class SessionRegistry:
    """Fetches and filters active sessions from the adapter."""

    def __init__(self, adapter_url: str, session: aiohttp.ClientSession) -> None:
        self._adapter_url = adapter_url.rstrip("/")
        self._session = session

    async def list_sessions(self) -> list[SessionInfo]:
        """Return sessions from the adapter (routing-active first)."""
        url = f"{self._adapter_url}/sessions"
        try:
            async with self._session.get(url) as resp:
                if resp.status != 200:
                    logger.warning("GET /sessions failed: %s", resp.status)
                    return []
                data = await resp.json()
        except Exception as exc:
            logger.warning("Failed to list sessions: %s", exc)
            return []

        sessions: list[SessionInfo] = []
        for row in data.get("sessions", []):
            source = str(row.get("source", ""))
            if source in SKIP_SOURCES:
                continue
            sessions.append(
                SessionInfo(
                    id=str(row["id"]),
                    source=source,
                    user_id=row.get("user_id"),
                    title=row.get("title"),
                    started_at=float(row.get("started_at", 0)),
                    message_count=int(row.get("message_count", 0)),
                    active=bool(row.get("active", False)),
                )
            )
        # Prefer Hermes routing-active sessions, then newest started_at.
        sessions.sort(key=lambda s: (s.active, s.started_at), reverse=True)
        return sessions

    @staticmethod
    def _preferred_for_source(
        sessions: list[SessionInfo], source: str
    ) -> list[SessionInfo]:
        """Sessions for *source*, preferring routing-active when any exist."""
        matches = [s for s in sessions if s.source == source]
        if not matches:
            return []
        active = [s for s in matches if s.active]
        return active if active else matches

    async def find_session_for_source(self, source: str) -> Optional[SessionInfo]:
        """Return the routing-active (else newest) session for a source."""
        if source in SKIP_SOURCES:
            if source == "cli":
                logger.debug("Skipping CLI source (see TODO.md)")
            return None
        preferred = self._preferred_for_source(await self.list_sessions(), source)
        return preferred[0] if preferred else None

    async def find_best_session(
        self,
        target_source: str,
        fallback_sources: list[str],
    ) -> Optional[SessionInfo]:
        """Find the active session matching target source, then fallbacks."""
        sessions = await self.list_sessions()
        for source in [target_source, *fallback_sources]:
            if source in SKIP_SOURCES:
                if source == "cli":
                    logger.debug("Skipping CLI fallback (see TODO.md)")
                continue
            preferred = self._preferred_for_source(sessions, source)
            if preferred:
                return preferred[0]
        return None

    async def find_sessions_for_sources(
        self,
        sources: list[str],
        max_targets: int = 1,
        broadcast: bool = False,
    ) -> list[SessionInfo]:
        """Find routing-active sessions for one or more sources."""
        sessions = await self.list_sessions()
        matched: list[SessionInfo] = []
        for source in sources:
            if source in SKIP_SOURCES:
                continue
            preferred = self._preferred_for_source(sessions, source)
            for session in preferred:
                matched.append(session)
                if not broadcast:
                    return matched[:max_targets]
        if broadcast:
            return matched
        return matched[:max_targets]

    async def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """Look up a session by ID."""
        for session in await self.list_sessions():
            if session.id == session_id:
                return session
        return None

    async def get_sessions_by_ids(self, session_ids: list[str]) -> list[SessionInfo]:
        """Look up multiple sessions by ID."""
        wanted = set(session_ids)
        return [s for s in await self.list_sessions() if s.id in wanted]
