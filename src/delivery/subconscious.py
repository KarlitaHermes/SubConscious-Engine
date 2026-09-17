"""SubConscious Adapter HTTP client for multi-session delivery."""

from __future__ import annotations

import logging
from typing import Any, Optional

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
        adapter_url: Optional[str] = None,
    ) -> DeliveryResult:
        """Inject a message into a single session."""
        base = (adapter_url or self._adapter_url).rstrip("/")
        url = f"{base}/inject"
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
                    logger.info("Injected into session %s via %s", session_id, base)
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
        *,
        adapter_url: Optional[str] = None,
    ) -> list[DeliveryResult]:
        """Inject the same message into multiple sessions concurrently."""
        import asyncio

        tasks = [
            self.inject_prompt(s.id, text, adapter_url=adapter_url) for s in sessions
        ]
        return list(await asyncio.gather(*tasks))

    async def list_sessions_raw(
        self,
        *,
        adapter_url: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """GET /sessions with no source filter (includes api_server Worker sticky)."""
        base = (adapter_url or self._adapter_url).rstrip("/")
        url = f"{base}/sessions"
        try:
            http = await self._get_session()
            async with http.get(url) as resp:
                if resp.status != 200:
                    logger.warning("GET %s failed: %s", url, resp.status)
                    return []
                data = await resp.json()
        except Exception as exc:
            logger.warning("GET %s error: %s", url, exc)
            return []
        rows = data.get("sessions") if isinstance(data, dict) else None
        return list(rows) if isinstance(rows, list) else []

    async def bootstrap_api_session(
        self,
        gateway_url: str,
        api_key: str,
        *,
        model: str = "karla-worker",
    ) -> bool:
        """Open a Worker api_server turn so /sessions has something to pin."""
        base = gateway_url.rstrip("/")
        url = f"{base}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": "SE sticky bootstrap. Reply: WORKER_READY",
                }
            ],
            "max_tokens": 32,
        }
        try:
            http = await self._get_session()
            async with http.post(url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    logger.info("Bootstrapped Worker api_server session via %s", base)
                    return True
                body = await resp.text()
                logger.warning(
                    "Worker bootstrap failed HTTP %s: %s", resp.status, body[:200]
                )
                return False
        except Exception as exc:
            logger.warning("Worker bootstrap error: %s", exc)
            return False


def pick_worker_session(rows: list[dict[str, Any]]) -> Optional[str]:
    """Prefer active subconscious-origin api_server, else any api_server, else any active."""
    if not rows:
        return None

    def score(row: dict[str, Any]) -> tuple:
        source = str(row.get("source") or "")
        uid = str(row.get("user_id") or "")
        active = bool(row.get("active"))
        started = float(row.get("started_at") or 0)
        return (
            1 if source == "api_server" else 0,
            1 if uid == "subconscious" else 0,
            1 if active else 0,
            started,
        )

    best = max(rows, key=score)
    sid = str(best.get("id") or "").strip()
    return sid or None
