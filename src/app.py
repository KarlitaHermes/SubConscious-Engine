"""Main application — async event router."""

from __future__ import annotations

import asyncio
import logging
import signal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

import aiohttp

from src.config import Config
from src.delivery.sessions import SessionRegistry
from src.delivery.subconscious import SubConsciousClient
from src.events.bus import EventBus
from src.router.router import Router
from src.sources.file_watcher import FileEventSource
from src.sources.idle import IdleEventSource
from src.sources.inbox_watcher import InboxEventSource
from src.sources.rest_poller import RestPollEventSource
from src.sources.rest_server import RestEventSource
from src.sources.vault_rules import VaultRulesEventSource
from src.state import StateManager

logger = logging.getLogger(__name__)


class App:
    """Coordinates event sources, router, and delivery."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._running = False
        self._bus = EventBus()
        self._state = StateManager(config.state.file)
        self._http: Optional[aiohttp.ClientSession] = None
        self._delivery: Optional[SubConsciousClient] = None
        self._registry: Optional[SessionRegistry] = None
        self._router: Optional[Router] = None
        self._sources: list = []
        self._tasks: list[asyncio.Task] = []

    async def run(self) -> None:
        """Run until shutdown signal."""
        self._setup_logging()
        self._running = True
        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(connect=5, total=15),
        )
        self._delivery = SubConsciousClient(self._config.adapter.url, self._http)
        self._registry = SessionRegistry(self._config.adapter.url, self._http)
        self._router = Router(self._config, self._registry, self._delivery, self._state)

        self._install_signal_handlers()
        await self._start_sources()
        self._tasks.append(asyncio.create_task(self._consume_loop()))

        logger.info("SubConscious Engine started")
        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            await self.shutdown()

    async def _consume_loop(self) -> None:
        """Consume events from the bus and route them."""
        assert self._router is not None
        async for event in self._bus.consume():
            try:
                results = await self._router.handle(event)
                ok = sum(1 for r in results if r.success)
                logger.info(
                    "Event %s type=%s delivered %d/%d",
                    event.id,
                    event.event_type,
                    ok,
                    len(results),
                )
            except Exception:
                logger.exception("Router error for event %s", event.id)

    async def _start_sources(self) -> None:
        """Start all configured entry points."""
        for entry_point in self._config.entry_points:
            if not entry_point.enabled:
                continue
            if entry_point.type == "directory":
                handler = entry_point.handle.handler
                if handler == "inbox":
                    src = InboxEventSource(
                        entry_point,
                        self._state,
                        vault_root=self._config.idle.vault_root,
                    )
                elif handler == "vault_rules":
                    inbox_dir = self._find_inbox_dir()
                    src = VaultRulesEventSource(
                        entry_point,
                        self._state,
                        vault_root=self._config.idle.vault_root,
                        inbox_dir=inbox_dir,
                    )
                elif handler == "event_file":
                    src = FileEventSource(entry_point)
                else:
                    logger.warning(
                        "Unknown directory handler %r on %s — using event_file",
                        handler,
                        entry_point.id,
                    )
                    src = FileEventSource(entry_point)
                self._sources.append(src)
                self._tasks.append(asyncio.create_task(src.start(self._bus)))
            elif entry_point.type == "http":
                src = RestEventSource(
                    entry_point,
                    self._state,
                    default_cooldown_minutes=self._config.idle.cooldown_minutes,
                )
                self._sources.append(src)
                self._tasks.append(asyncio.create_task(src.start(self._bus)))
            elif entry_point.type == "http_poll":
                assert self._http is not None
                src = RestPollEventSource(entry_point, self._state, self._http)
                self._sources.append(src)
                self._tasks.append(asyncio.create_task(src.start(self._bus)))
            elif entry_point.type == "idle":
                assert self._registry is not None
                src = IdleEventSource(
                    self._config,
                    self._registry,
                    self._state,
                    entry_point_id=entry_point.id,
                )
                self._sources.append(src)
                self._tasks.append(asyncio.create_task(src.start(self._bus)))
            else:
                logger.warning(
                    "Unknown entry point type %r (%s)",
                    entry_point.type,
                    entry_point.id,
                )

    def _find_inbox_dir(self) -> Optional[Path]:
        """Return inbox directory path if configured as an entry point."""
        for entry_point in self._config.entry_points:
            if entry_point.type == "directory" and entry_point.handle.handler == "inbox":
                return entry_point.path
        return self._config.idle.vault_root / "COMMS" / "Inbox"

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._request_shutdown)

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested")
        self._running = False
        self._bus.close()

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self._bus.close()
        for src in self._sources:
            await src.stop()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._delivery:
            await self._delivery.close()
        if self._http:
            await self._http.close()
        self._state.save()
        logger.info("SubConscious Engine stopped")

    def _setup_logging(self) -> None:
        log_cfg = self._config.logging
        root = logging.getLogger()
        root.setLevel(getattr(logging, log_cfg.level.upper(), logging.INFO))
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
        log_cfg.file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_cfg.file,
            maxBytes=log_cfg.max_bytes,
            backupCount=log_cfg.backup_count,
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
