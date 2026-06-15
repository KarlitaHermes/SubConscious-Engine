"""Watch a directory for event files and publish them to the bus."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Set

import yaml

from src.config.models import EntryPoint
from src.events.bus import EventBus
from src.events.models import Event, EventSourceKind

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = {".json", ".yaml", ".yml", ".txt"}


class FileEventSource:
    """Poll a drop directory for new event files."""

    def __init__(self, entry_point: EntryPoint) -> None:
        if entry_point.path is None:
            raise ValueError(f"Directory entry point {entry_point.id!r} requires path")
        self._entry_point = entry_point
        self._directory = entry_point.path
        self._poll_interval = entry_point.poll_interval_seconds
        self._archive_dir = entry_point.archive_dir or (entry_point.path / "processed")
        self._handle = entry_point.handle
        self._seen: Set[str] = set()
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self, bus: EventBus) -> None:
        """Start polling the directory."""
        self._directory.mkdir(parents=True, exist_ok=True)
        self._archive_dir.mkdir(parents=True, exist_ok=True)
        self._running = True
        self._task = asyncio.create_task(self._poll_loop(bus))
        logger.info(
            "File event source %s watching %s (handler=%s)",
            self._entry_point.id,
            self._directory,
            self._handle.handler,
        )

    async def stop(self) -> None:
        """Stop the poll loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _poll_loop(self, bus: EventBus) -> None:
        while self._running:
            try:
                await self._scan_directory(bus)
            except Exception:
                logger.exception("File source scan error")
            await asyncio.sleep(self._poll_interval)

    async def _scan_directory(self, bus: EventBus) -> None:
        for path in sorted(self._directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            key = f"{path.name}:{path.stat().st_mtime_ns}"
            if key in self._seen:
                continue
            event = self._parse_file(path)
            if event is None:
                continue
            if await bus.publish(event):
                self._seen.add(key)
                await asyncio.to_thread(self._archive_file, path)

    def _parse_file(self, path: Path) -> Optional[Event]:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            suffix = path.suffix.lower()
            if suffix == ".txt":
                return Event(
                    text=raw,
                    event_type=self._handle.default_event_type,
                    source=EventSourceKind.FILE,
                    entry_point=self._entry_point.id,
                    priority=self._handle.default_priority,
                    metadata={"file": str(path.name), "handler": self._handle.handler},
                )
            data = json.loads(raw) if suffix == ".json" else yaml.safe_load(raw)
            if not isinstance(data, dict):
                logger.warning("Invalid event file %s: expected object", path)
                return None
            event = Event.from_dict(data, EventSourceKind.FILE)
            event.entry_point = event.entry_point or self._entry_point.id
            if "event_type" not in data and "type" not in data:
                event.event_type = self._handle.default_event_type
            if "priority" not in data:
                event.priority = self._handle.default_priority
            event.metadata.setdefault("file", path.name)
            event.metadata.setdefault("handler", self._handle.handler)
            return event
        except Exception as exc:
            logger.error("Failed to parse event file %s: %s", path, exc)
            return None

    def _archive_file(self, path: Path) -> None:
        dest = self._archive_dir / path.name
        if dest.exists():
            dest = self._archive_dir / f"{path.stem}_{int(path.stat().st_mtime)}{path.suffix}"
        path.rename(dest)
