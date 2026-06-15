"""Tests for router skip when task in progress."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.events.models import Event, EventSourceKind
from src.router.router import Router
from src.state import StateManager
from tests.conftest import make_config, make_session


@pytest.mark.asyncio
async def test_handle_skips_when_task_in_progress(tmp_path, mock_registry, mock_delivery) -> None:
    state = StateManager(tmp_path / "state.yaml")
    state.record_ack("maintenance", 60, status="in_progress")

    config = make_config(
        tmp_path,
        rules=[{"event_type": "maintenance", "target_sources": ["telegram"]}],
    )
    session = make_session()
    mock_registry.find_sessions_for_sources.return_value = [session]

    router = Router(config, mock_registry, mock_delivery, state)
    event = Event(
        text="maintenance again",
        event_type="maintenance",
        source=EventSourceKind.IDLE,
        cooldown_key="maintenance",
    )

    results = await router.handle(event)
    assert results == []
    mock_delivery.inject_many.assert_not_awaited()
