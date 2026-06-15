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


class SessionRegistry:
    """Fetches and filters active sessions from the adapter."""

    def __init__(self, adapter_url: str, session: aiohttp.ClientSession) -> None:
        self._adapter_url = adapter_url.rstrip("/")
        self._session = session

    async def list_sessions(self) -> list[SessionInfo]:
        """Return all active sessions from the adapter."""
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
                )
            )
        sessions.sort(key=lambda s: s.started_at, reverse=True)
        return sessions

    async def find_best_session(
        self,
        target_source: str,
        fallback_sources: list[str],
    ) -> Optional[SessionInfo]:
        """Find the newest session matching target source, then fallbacks."""
        sessions = await self.list_sessions()
        for source in [target_source, *fallback_sources]:
            if source in SKIP_SOURCES:
                if source == "cli":
                    logger.debug("Skipping CLI fallback (see TODO.md)")
                continue
            for session in sessions:
                if session.source == source:
                    return session
        return None

    async def find_sessions_for_sources(
        self,
        sources: list[str],
        max_targets: int = 1,
        broadcast: bool = False,
    ) -> list[SessionInfo]:
        """Find sessions for one or more sources."""
        sessions = await self.list_sessions()
        matched: list[SessionInfo] = []
        for source in sources:
            if source in SKIP_SOURCES:
                continue
            for session in sessions:
                if session.source == source:
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
