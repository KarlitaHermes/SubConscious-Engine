"""Inbound REST API for receiving events."""

from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web

from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind

logger = logging.getLogger(__name__)


class RestEventSource:
    """aiohttp server that accepts POST /events."""

    def __init__(self, entry_point: EntryPoint) -> None:
        self._entry_point = entry_point
        self._host = entry_point.host
        self._port = entry_point.port
        self._api_key = entry_point.api_key
        self._handle = entry_point.handle
        self._bus: Optional[EventBus] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self, bus: EventBus) -> None:
        """Start the HTTP server."""
        self._bus = bus
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/events", self._handle_events)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info(
            "REST event source %s listening on %s:%d",
            self._entry_point.id,
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "service": "subconscious-engine"})

    async def _handle_events(self, request: web.Request) -> web.Response:
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Body must be a JSON object"}, status=400)
        if not str(data.get("text", "")).strip():
            return web.json_response({"error": "text is required"}, status=400)

        event = Event.from_dict(data, EventSourceKind.REST)
        event.entry_point = event.entry_point or self._entry_point.id
        if "event_type" not in data and "type" not in data:
            event.event_type = self._handle.default_event_type
        if "priority" not in data:
            event.priority = self._handle.default_priority

        if self._bus is None:
            return web.json_response({"error": "Event bus not ready"}, status=503)
        accepted = await self._bus.publish(event)
        if not accepted:
            return web.json_response({"error": "Event bus unavailable"}, status=503)
        return web.json_response({"ok": True, "event_id": event.id}, status=202)

    def _check_auth(self, request: web.Request) -> bool:
        if not self._api_key:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() == self._api_key
        return request.headers.get("X-API-Key", "") == self._api_key
