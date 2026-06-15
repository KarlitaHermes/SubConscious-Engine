"""Tests for outbound HTTP poll source (isolated — no full engine)."""

from __future__ import annotations

from pathlib import Path

import aiohttp
import pytest
from aiohttp import web

from src.config.models import EntryPoint, HandleConfig
from src.config.parser import parse_entry_point
from src.events.bus import EventBus
from src.sources.rest_poller import RestPollEventSource
from src.state import StateManager


@pytest.fixture
async def poll_stub_url():
    """Serve canned JSON on a random free port (not 8770/8771)."""

    async def handle(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "events": [
                    {
                        "id": "stub-1",
                        "text": "[SUBCONSCIOUS ENGINE TEST] poll stub",
                        "event_type": "custom",
                    },
                    {"id": "stub-2", "text": "second item", "event_type": "custom"},
                ],
            },
        )

    app = web.Application()
    app.router.add_get("/events", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/events"
    await runner.cleanup()


@pytest.mark.asyncio
async def test_poll_publishes_new_items_only(poll_stub_url: str, tmp_path: Path) -> None:
    state = StateManager(tmp_path / "state.yaml")
    entry_point = EntryPoint(
        id="test_poll",
        type="http_poll",
        url=poll_stub_url,
        poll_interval_seconds=60,
        handle=HandleConfig(items_key="events", default_event_type="custom"),
    )
    bus = EventBus()

    async with aiohttp.ClientSession() as http:
        source = RestPollEventSource(entry_point, state, http)
        await source._poll_once(bus)

    events = []
    bus.close()
    async for event in bus.consume():
        events.append(event)

    assert len(events) == 2
    assert events[0].entry_point == "test_poll"
    assert state.is_poll_item_seen("test_poll", "stub-1") is True

    bus2 = EventBus()
    async with aiohttp.ClientSession() as http:
        source = RestPollEventSource(entry_point, state, http)
        await source._poll_once(bus2)

    bus2.close()
    second_pass = [e async for e in bus2.consume()]
    assert second_pass == []


@pytest.mark.asyncio
async def test_poll_skips_http_errors(tmp_path: Path) -> None:
    async def fail(_request: web.Request) -> web.Response:
        return web.Response(status=500, text="error")

    app = web.Application()
    app.router.add_get("/bad", fail)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets if site._server else []
    port = sockets[0].getsockname()[1]
    url = f"http://127.0.0.1:{port}/bad"

    try:
        state = StateManager(tmp_path / "state.yaml")
        entry_point = EntryPoint(id="bad_poll", type="http_poll", url=url)
        bus = EventBus()

        async with aiohttp.ClientSession() as http:
            source = RestPollEventSource(entry_point, state, http)
            await source._poll_once(bus)

        bus.close()
        events = [e async for e in bus.consume()]
        assert events == []
    finally:
        await runner.cleanup()


def test_parse_http_poll_entry_point() -> None:
    ep = parse_entry_point(
        {
            "id": "feed",
            "type": "http_poll",
            "url": "http://example.com/events",
            "method": "get",
            "headers": {"Accept": "application/json"},
            "handle": {"items_key": "events", "id_field": "uuid"},
        },
    )
    assert ep.type == "http_poll"
    assert ep.url == "http://example.com/events"
    assert ep.method == "GET"
    assert ep.headers["Accept"] == "application/json"
    assert ep.handle.items_key == "events"
    assert ep.handle.id_field == "uuid"
