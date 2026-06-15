"""Tests for agent ack endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from src.config.models import EntryPoint
from src.sources.rest_server import RestEventSource
from src.state import StateManager


@pytest.fixture
async def ack_server(tmp_path: Path):
    state = StateManager(tmp_path / "state.yaml")
    entry_point = EntryPoint(id="api", type="http", host="127.0.0.1", port=0)
    source = RestEventSource(entry_point, state, default_cooldown_minutes=60)

    app = web.Application()
    app.router.add_post("/ack", source._handle_ack)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    base = f"http://127.0.0.1:{port}"

    yield base, state
    await runner.cleanup()


@pytest.mark.asyncio
async def test_ack_sets_cooldown_and_agent_activity(ack_server) -> None:
    import aiohttp

    base, state = ack_server
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{base}/ack",
            json={"cooldown_key": "idle_engine", "status": "done", "reset_idle_period": True},
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True

    assert state.is_in_cooldown(60, key="idle_engine") is True
    assert state.last_agent_handled is not None
    assert state.idle_period_active is False


@pytest.mark.asyncio
async def test_ack_in_progress_without_cooldown(ack_server) -> None:
    import aiohttp

    base, state = ack_server
    async with aiohttp.ClientSession() as http:
        async with http.post(
            f"{base}/ack",
            json={"cooldown_key": "maintenance", "status": "in_progress"},
        ) as resp:
            assert resp.status == 200
            body = await resp.json()
            assert body["status"] == "in_progress"
            assert body["cooldown_minutes"] is None

    assert state.is_task_in_progress("maintenance") is True
    assert state.is_in_cooldown(60, key="maintenance") is False
    assert state.last_agent_handled is not None


@pytest.mark.asyncio
async def test_ack_requires_cooldown_key(ack_server) -> None:
    import aiohttp

    base, _state = ack_server
    async with aiohttp.ClientSession() as http:
        async with http.post(f"{base}/ack", json={}) as resp:
            assert resp.status == 400
