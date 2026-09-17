"""Worker sticky pin heal + pick_worker_session."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.delivery.subconscious import pick_worker_session
from src.events.models import DeliveryResult, Event, EventSourceKind
from src.router.router import Router
from src.state import StateManager
from tests.conftest import make_config


def _fresh_state(tmp_path):
    return StateManager(tmp_path / "state.yaml")


def test_pick_worker_session_prefers_subconscious_api() -> None:
    rows = [
        {"id": "api-old", "source": "api_server", "user_id": None, "active": True, "started_at": 1},
        {
            "id": "sticky",
            "source": "api_server",
            "user_id": "subconscious",
            "active": True,
            "started_at": 2,
        },
        {"id": "tg", "source": "telegram", "user_id": "1", "active": True, "started_at": 99},
    ]
    assert pick_worker_session(rows) == "sticky"


@pytest.mark.asyncio
async def test_preferred_inject_heals_on_failure(tmp_path) -> None:
    mock_registry = AsyncMock()
    mock_delivery = AsyncMock()
    mock_delivery.inject_prompt.side_effect = [
        DeliveryResult(session_id="dead", success=False, error="Session dead not found"),
        DeliveryResult(session_id="sticky-new", success=True),
    ]
    mock_delivery.list_sessions_raw.return_value = [
        {
            "id": "sticky-new",
            "source": "api_server",
            "user_id": "subconscious",
            "active": True,
            "started_at": 10,
        }
    ]
    mock_delivery.bootstrap_api_session.return_value = False

    config = make_config(
        tmp_path,
        rules=[
            {
                "event_type": "maintenance",
                "preferred_session_id": "dead",
                "inject_url": "http://127.0.0.1:8772",
                "target_sources": ["api_server"],
            }
        ],
    )
    state = _fresh_state(tmp_path)
    router = Router(config, mock_registry, mock_delivery, state)
    event = Event(
        text="nudge",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        cooldown_key="heal_test",
    )
    results = await router.handle(event)
    assert len(results) == 1
    assert results[0].success is True
    assert results[0].session_id == "sticky-new"
    assert state.worker_preferred_session_id == "sticky-new"
    assert mock_delivery.inject_prompt.await_count == 2
