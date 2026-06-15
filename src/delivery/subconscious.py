"""SubConscious Adapter HTTP client for multi-session delivery."""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from src.delivery.sessions import SessionInfo
from src.events.models import DeliveryResult

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(connect=5, total=15)


class SubConsciousClient:
    """HTTP client for adapter inject + session listing."""

    def __init__(
        self,
        adapter_url: str,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> None:
        self._adapter_url = adapter_url.rstrip("/")
        self._session = session
        self._owns_session = session is None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session if owned."""
        if self._owns_session and self._session:
            await self._session.close()
            self._session = None

    async def inject_prompt(
        self,
        session_id: str,
        text: str,
        *,
        delivery: str = "queue",
    ) -> DeliveryResult:
        """Inject a message into a single session."""
        url = f"{self._adapter_url}/inject"
        payload = {
            "session_id": session_id,
            "text": text,
            "delivery": delivery,
        }
        try:
            http = await self._get_session()
            async with http.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("ok"):
                    logger.info("Injected into session %s", session_id)
                    return DeliveryResult(session_id=session_id, success=True)
                error = data.get("error", f"HTTP {resp.status}")
                logger.warning("Inject failed for %s: %s", session_id, error)
                return DeliveryResult(session_id=session_id, success=False, error=str(error))
        except Exception as exc:
            logger.warning("Inject error for %s: %s", session_id, exc)
            return DeliveryResult(session_id=session_id, success=False, error=str(exc))

    async def inject_many(
        self,
        text: str,
        sessions: list[SessionInfo],
    ) -> list[DeliveryResult]:
        """Inject the same message into multiple sessions concurrently."""
        import asyncio

        tasks = [self.inject_prompt(s.id, text) for s in sessions]
        return list(await asyncio.gather(*tasks))
