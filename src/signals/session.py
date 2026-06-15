"""Gateway session activity signals."""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

INJECTED_PREFIXES = ("[SUBCONSCIOUS", "[IDLE ENGINE", "[SUBCONSCIOUS ENGINE")
DEFAULT_TIMEOUT = aiohttp.ClientTimeout(connect=5, total=15)


async def get_last_human_activity(
    gateway_url: str,
    api_key: str,
    session_id: str,
) -> Optional[float]:
    """Return the timestamp of the last human user message in a session."""
    url = f"{gateway_url.rstrip('/')}/api/sessions/{session_id}/messages"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with aiohttp.ClientSession(timeout=DEFAULT_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("GET messages failed for %s: %s", session_id, resp.status)
                    return None
                data = await resp.json()
    except Exception as exc:
        logger.warning("Failed to fetch messages for %s: %s", session_id, exc)
        return None

    last_ts: Optional[float] = None
    for message in data.get("data", []):
        if message.get("role") != "user":
            continue
        content = (message.get("content") or "").lstrip()
        if content.startswith(INJECTED_PREFIXES):
            continue
        ts = message.get("timestamp")
        if ts is not None and (last_ts is None or float(ts) > last_ts):
            last_ts = float(ts)
    return last_ts
