"""Tests for SubConscious adapter HTTP client."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.delivery.subconscious import SubConsciousClient


def _mock_http_session(*, status: int = 200, body: dict | None = None) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = status
    mock_resp.json = AsyncMock(return_value=body or {"ok": True})
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=mock_cm)
    return mock_http


@pytest.mark.asyncio
async def test_inject_prompt_sends_delivery_queue_by_default() -> None:
    client = SubConsciousClient("http://127.0.0.1:8769")
    client._session = _mock_http_session()

    result = await client.inject_prompt("sess-1", "[SUBCONSCIOUS] test nudge")

    assert result.success is True
    client._session.post.assert_called_once()
    _url, kwargs = client._session.post.call_args
    assert kwargs["json"] == {
        "session_id": "sess-1",
        "text": "[SUBCONSCIOUS] test nudge",
        "delivery": "queue",
    }


@pytest.mark.asyncio
async def test_inject_prompt_can_request_interrupt() -> None:
    client = SubConsciousClient("http://127.0.0.1:8769")
    client._session = _mock_http_session()

    await client.inject_prompt("sess-1", "urgent", delivery="interrupt")

    _url, kwargs = client._session.post.call_args
    assert kwargs["json"]["delivery"] == "interrupt"
