"""Inbound REST API for receiving events and agent acknowledgements."""

from __future__ import annotations

import logging
from typing import Optional

from aiohttp import web

from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind
from src.state import ACK_STATUS_DONE, ACK_STATUS_IN_PROGRESS, StateManager

logger = logging.getLogger(__name__)


class RestEventSource:
    """aiohttp server — POST /events and POST /ack."""

    def __init__(
        self,
        entry_point: EntryPoint,
        state: StateManager,
        *,
        default_cooldown_minutes: int = 60,
    ) -> None:
        self._entry_point = entry_point
        self._host = entry_point.host
        self._port = entry_point.port
        self._api_key = entry_point.api_key
        self._handle = entry_point.handle
        self._state = state
        self._default_cooldown = default_cooldown_minutes
        self._bus: Optional[EventBus] = None
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None

    async def start(self, bus: EventBus) -> None:
        """Start the HTTP server."""
        self._bus = bus
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        app.router.add_post("/events", self._handle_events)
        app.router.add_post("/ack", self._handle_ack)
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

    async def _handle_ack(self, request: web.Request) -> web.Response:
        """Agent confirms it handled a subconscious item — refresh cooldowns."""
        if not self._check_auth(request):
            return web.json_response({"error": "Unauthorized"}, status=401)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)
        if not isinstance(data, dict):
            return web.json_response({"error": "Body must be a JSON object"}, status=400)

        cooldown_key = str(data.get("cooldown_key", "")).strip()
        if not cooldown_key:
            return web.json_response({"error": "cooldown_key is required"}, status=400)

        minutes = int(data.get("cooldown_minutes", self._default_cooldown))
        status = str(data.get("status", ACK_STATUS_DONE)).strip().lower()
        if status not in (ACK_STATUS_IN_PROGRESS, ACK_STATUS_DONE, "completed"):
            return web.json_response(
                {"error": "status must be in_progress, done, or completed"},
                status=400,
            )

        self._state.record_ack(
            cooldown_key,
            minutes,
            status=status,
            reset_idle_period=bool(data.get("reset_idle_period", False)),
            event_id=data.get("event_id"),
        )
        return web.json_response(
            {
                "ok": True,
                "cooldown_key": cooldown_key,
                "status": status,
                "cooldown_minutes": minutes if status != ACK_STATUS_IN_PROGRESS else None,
            },
            status=200,
        )

    def _check_auth(self, request: web.Request) -> bool:
        if not self._api_key:
            return True
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip() == self._api_key
        return request.headers.get("X-API-Key", "") == self._api_key
