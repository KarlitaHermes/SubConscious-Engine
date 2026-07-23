"""Tests for SessionRegistry active-route selection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.delivery.sessions import SessionRegistry


def _mock_http(*, sessions: list[dict]) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"sessions": sessions})
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_cm.__aexit__ = AsyncMock(return_value=None)
    mock_http = MagicMock()
    mock_http.get = MagicMock(return_value=mock_cm)
    return mock_http


@pytest.mark.asyncio
async def test_find_session_for_source_prefers_active_over_newer() -> None:
    http = _mock_http(
        sessions=[
            {
                "id": "sess_new_stale",
                "source": "telegram",
                "user_id": "1",
                "title": "stale open",
                "started_at": 3000.0,
                "message_count": 1,
                "active": False,
            },
            {
                "id": "sess_active",
                "source": "telegram",
                "user_id": "1",
                "title": "routed",
                "started_at": 1000.0,
                "message_count": 10,
                "active": True,
            },
        ]
    )
    registry = SessionRegistry("http://127.0.0.1:8769", http)
    session = await registry.find_session_for_source("telegram")
    assert session is not None
    assert session.id == "sess_active"
    assert session.active is True


@pytest.mark.asyncio
async def test_find_session_falls_back_to_newest_without_active_flags() -> None:
    http = _mock_http(
        sessions=[
            {
                "id": "sess_old",
                "source": "telegram",
                "user_id": "1",
                "title": None,
                "started_at": 1000.0,
                "message_count": 1,
            },
            {
                "id": "sess_new",
                "source": "telegram",
                "user_id": "1",
                "title": None,
                "started_at": 2000.0,
                "message_count": 1,
            },
        ]
    )
    registry = SessionRegistry("http://127.0.0.1:8769", http)
    session = await registry.find_session_for_source("telegram")
    assert session is not None
    assert session.id == "sess_new"
