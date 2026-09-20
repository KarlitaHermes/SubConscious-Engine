"""Event router — resolves targets and dispatches delivery."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from src.config import Config
from src.delivery.sessions import SessionInfo, SessionRegistry
from src.delivery.subconscious import SubConsciousClient, pick_worker_session
from src.events.models import DeliveryResult, Event
from src.notify_gate import NotifyGate, SuppressReason
from src.router.rules import RouteRule
from src.state import StateManager

logger = logging.getLogger(__name__)

SKIP_SOURCES = frozenset({"cron", "subagent", "api_server"})


class Router:
    """Resolves event targets and delivers to one or more sessions."""

    def __init__(
        self,
        config: Config,
        registry: SessionRegistry,
        delivery: SubConsciousClient,
        state: StateManager,
        *,
        notify_gate: NotifyGate | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._delivery = delivery
        self._state = state
        self._gate = notify_gate or NotifyGate(config)

    def _allowed_sources(self, event: Event, rule: RouteRule) -> list[str]:
        """Sources permitted for this event under the matched routing rule."""
        sources = rule.target_sources or (
            [event.preferred_source] if event.preferred_source else []
        )
        if not sources:
            sources = [self._config.idle.target_source, *self._config.idle.fallback_sources]
        return [s for s in sources if s not in SKIP_SOURCES]

    async def handle(self, event: Event, *, now: datetime | None = None) -> list[DeliveryResult]:
        """Route an event and deliver to resolved session(s)."""
        reason = self._gate.check(self._state, event, now=now)
        if reason is SuppressReason.DEFER_PREFERRED_WINDOW:
            self._park_deferred(event, now=now)
            return []
        if reason is not None:
            self._log_suppressed(event, reason)
            return []

        rule = self._gate.resolve_rule(event, now=now)
        assert rule is not None
        cooldown_key = self._gate.cooldown_key(event)

        # Inbox recipient suffix (-face|-worker|…) overrides default Face inject.
        if event.event_type in ("inbox_notify", "inbox_item"):
            recipient = str((event.metadata or {}).get("inbox_recipient") or "face")
            if recipient == "worker":
                results = await self._deliver_inbox_worker(event)
                return self._finish_delivery(event, results, cooldown_key)
            if recipient in ("dumb", "musickarla"):
                # No subconscious adapters on those profiles yet — Face, with an honest prefix.
                logger.warning(
                    "Inbox recipient %s has no adapter; delivering to Face with prefix (%s)",
                    recipient,
                    event.id,
                )
                event = Event(
                    text=(
                        f"[inbox recipient={recipient} — no adapter; delivered to Face]\n\n"
                        f"{event.text}"
                    ),
                    event_type=event.event_type,
                    source=event.source,
                    entry_point=event.entry_point,
                    task_id=event.task_id,
                    id=event.id,
                    preferred_target=event.preferred_target,
                    preferred_source=event.preferred_source,
                    targets=list(event.targets),
                    priority=event.priority,
                    cooldown_key=event.cooldown_key,
                    metadata={**(event.metadata or {}), "inbox_recipient": "face",
                              "inbox_recipient_requested": recipient},
                    created_at=event.created_at,
                )
        # Script mode: start a board/pipeline without injecting Face/Worker.
        if rule.mode == "script" and rule.script:
            results = await self._run_script(event, rule)
            return self._finish_delivery(event, results, cooldown_key)

        # Sticky Worker session pin — only when the rule asks for it.
        # Do NOT route Face telegram (e.g. inbox_notify) through Worker just
        # because a worker_preferred_session_id is set in state.
        if rule.preferred_session_id:
            results = await self._deliver_preferred(event, rule)
            success = any(r.success for r in results)
            if success and rule.inbox_report:
                self._write_inbox_report(event)
            return self._finish_delivery(event, results, cooldown_key)

        targets = await self._resolve_targets(event, rule)
        if not targets:
            logger.warning("No targets resolved for event %s type=%s", event.id, event.event_type)
            return []

        for session in targets:
            self._state.note_active_session(session.source, session.id)

        results = await self._delivery.inject_many(
            self._delivery_text(event),
            targets,
            adapter_url=rule.inject_url,
        )
        return self._finish_delivery(event, results, cooldown_key)

    def _finish_delivery(
        self,
        event: Event,
        results: list[DeliveryResult],
        cooldown_key: str,
    ) -> list[DeliveryResult]:
        """Record delivery, commit inbox fingerprints, clear deferred."""
        success = any(r.success for r in results)
        queued = any(getattr(r, "queued", False) for r in results if r.success)
        self._state.record_delivery(
            event_id=event.id,
            event_type=event.event_type,
            session_ids=[r.session_id for r in results if r.success],
            success=success,
            cooldown_key=cooldown_key,
            queued=queued,
        )
        if success:
            self._state.clear_deferred(cooldown_key)
            self._commit_inbox_file(event, queued=queued)
        return results

    def _commit_inbox_file(self, event: Event, *, queued: bool) -> None:
        """Mark inbox file processed only after surfaced delivery (Bug A/B)."""
        if event.event_type not in ("inbox_notify", "inbox_item"):
            return
        meta = event.metadata or {}
        filename = meta.get("file")
        fingerprint = meta.get("file_fingerprint")
        entry = event.entry_point or "inbox"
        if not filename or not fingerprint:
            return
        if queued:
            self._state.mark_inbox_inflight(entry, str(filename), str(fingerprint))
            logger.info(
                "Inbox %s queued — inflight until surface/ack or flush timeout",
                filename,
            )
            return
        self._state.mark_file_processed(entry, str(filename), str(fingerprint))

    def _preferred_pin(self, rule: RouteRule) -> str:
        return (
            self._state.worker_preferred_session_id
            or rule.preferred_session_id
            or self._config.worker.preferred_session_id
            or ""
        ).strip()

    def _worker_adapter_url(self, rule: RouteRule) -> str:
        return (
            (rule.inject_url or "").rstrip("/")
            or self._config.worker.adapter_url
            or self._config.adapter.url
        ).rstrip("/")

    async def _deliver_preferred(
        self, event: Event, rule: RouteRule
    ) -> list[DeliveryResult]:
        """Inject pinned Worker session; on failure re-list / bootstrap and re-pin."""
        adapter = self._worker_adapter_url(rule)
        text = self._delivery_text(event)
        pin = self._preferred_pin(rule)

        if pin:
            result = await self._delivery.inject_prompt(
                pin, text, adapter_url=adapter
            )
            if result.success:
                await self._refresh_worker_pin(adapter, fallback=pin)
                return [result]
            logger.warning(
                "Preferred session %s failed (%s) — healing Worker sticky",
                pin,
                result.error,
            )
        else:
            logger.warning("No Worker sticky pin — healing")

        healed = await self._heal_worker_session(adapter)
        if not healed:
            return [
                DeliveryResult(
                    session_id=pin or "worker:unhealed",
                    success=False,
                    error="Worker sticky heal failed",
                )
            ]

        result = await self._delivery.inject_prompt(
            healed, text, adapter_url=adapter
        )
        if result.success:
            await self._refresh_worker_pin(adapter, fallback=healed)
        return [result]

    async def _refresh_worker_pin(self, adapter: str, *, fallback: str) -> None:
        """After a successful inject, pin the live subconscious/api_server session."""
        rows = await self._delivery.list_sessions_raw(adapter_url=adapter)
        live = pick_worker_session(rows) or fallback
        self._state.set_worker_preferred_session_id(live)

    async def _heal_worker_session(self, adapter: str) -> Optional[str]:
        """Find or bootstrap a Worker api_server session; never fall back to Face."""
        rows = await self._delivery.list_sessions_raw(adapter_url=adapter)
        found = pick_worker_session(rows)
        if found:
            logger.info("Healed Worker sticky from adapter list → %s", found)
            self._state.set_worker_preferred_session_id(found)
            return found

        worker = self._config.worker
        api_key = self._config.gateway.api_key
        if not worker.gateway_url or not api_key:
            logger.error(
                "Worker heal: no sessions on %s and gateway bootstrap unavailable",
                adapter,
            )
            return None

        ok = await self._delivery.bootstrap_api_session(
            worker.gateway_url, api_key
        )
        if not ok:
            return None

        rows = await self._delivery.list_sessions_raw(adapter_url=adapter)
        found = pick_worker_session(rows)
        if found:
            logger.info("Healed Worker sticky via bootstrap → %s", found)
            self._state.set_worker_preferred_session_id(found)
            return found

        logger.error("Worker heal: bootstrap ok but /sessions still empty on %s", adapter)
        return None

    async def _run_script(self, event: Event, rule: RouteRule) -> list[DeliveryResult]:
        """Run deliver.script (e.g. start-music-pipeline) as board start."""
        import asyncio
        import os

        script = rule.script or ""
        logger.info("Event %s mode=script → %s", event.id, script)
        try:
            proc = await asyncio.create_subprocess_shell(
                script,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            # Brief settle — long monitors stay up; immediate crash → fail.
            await asyncio.sleep(3)
            if proc.returncode is None:
                logger.info("Script running (ok): %s pid=%s", script, proc.pid)
                return [DeliveryResult(session_id=f"script:{event.id}", success=True)]
            err = ""
            if proc.stderr:
                err = (await proc.stderr.read()).decode("utf-8", errors="replace")[:500]
            if proc.returncode == 0:
                return [DeliveryResult(session_id=f"script:{event.id}", success=True)]
            logger.warning("Script failed (%s): %s", proc.returncode, err)
            return [DeliveryResult(session_id=f"script:{event.id}", success=False, error=err)]
        except Exception as exc:
            logger.warning("Script error: %s", exc)
            return [DeliveryResult(session_id=f"script:{event.id}", success=False, error=str(exc))]

    def _park_deferred(self, event: Event, *, now: datetime | None = None) -> None:
        prefer_until = self._gate.prefer_until_ts(event, now=now)
        rule = self._gate.resolve_rule(event, now=now)
        hours = list(rule.preferred_window.hours) if rule and rule.preferred_window else []
        if prefer_until is None:
            logger.warning(
                "Event %s deferred without prefer_until — skipping park",
                event.id,
            )
            return
        key = self._gate.cooldown_key(event)
        self._state.park_deferred(
            key,
            event_type=event.event_type,
            text=event.text,
            source=event.source.value if hasattr(event.source, "value") else str(event.source),
            entry_point=event.entry_point,
            task_id=event.task_id,
            priority=event.priority,
            preferred_target=event.preferred_target,
            preferred_source=event.preferred_source,
            prefer_until=prefer_until,
            preferred_hours=hours,
            metadata=event.metadata,
            event_id=event.id,
        )
        self._gate.log_suppressed(
            event,
            SuppressReason.DEFER_PREFERRED_WINDOW,
            source="router",
        )

    def _log_suppressed(self, event: Event, reason: SuppressReason) -> None:
        cooldown_key = self._gate.cooldown_key(event)
        if reason is SuppressReason.NO_RULE:
            logger.info(
                "Event %s type=%s skipped — no applicable rule (time/priority)",
                event.id,
                event.event_type,
            )
        elif reason is SuppressReason.COOLDOWN:
            logger.info("Event %s in cooldown (%s)", event.id, cooldown_key)
        elif reason is SuppressReason.IN_PROGRESS:
            logger.info(
                "Event %s skipped — task in progress (%s)",
                event.id,
                cooldown_key,
            )
        elif reason is SuppressReason.NUDGE_BUDGET:
            fname = (event.metadata or {}).get("file") or cooldown_key
            logger.warning(
                "Event %s type=%s skipped — nudge budget exceeded (file=%s)",
                event.id,
                event.event_type,
                fname,
            )

    async def _deliver_inbox_worker(self, event: Event) -> list[DeliveryResult]:
        """Inject an Inbox notify into the Worker sticky session."""
        rule = RouteRule(
            event_type=event.event_type,
            target_sources=["api_server"],
            preferred_session_id=(
                self._state.worker_preferred_session_id
                or self._config.worker.preferred_session_id
                or None
            ),
            inject_url=self._config.worker.adapter_url or None,
        )
        return await self._deliver_preferred(event, rule)

    @staticmethod
    def _delivery_text(event: Event) -> str:
        """Append ack hint so Hermes knows which cooldown_key to confirm."""
        if not event.cooldown_key:
            return event.text
        return f"{event.text}\n\n[engine-ack:{event.cooldown_key}|in_progress,done]"

    def _write_inbox_report(self, event: Event) -> None:
        """Drop a notify-prefixed Inbox file so Face is paged via inbox_notify."""
        from pathlib import Path

        inbox = None
        for ep in self._config.entry_points:
            if ep.type == "directory" and getattr(ep.handle, "handler", None) == "inbox":
                raw = ep.path
                inbox = Path(raw).expanduser() if raw is not None else None
                break
        if inbox is None:
            inbox = Path.home() / "vault" / "COMMS" / "Inbox"
        try:
            inbox.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning("Inbox report mkdir failed: %s", exc)
            return

        window = (event.metadata or {}).get("window_start") or (event.metadata or {}).get("date") or ""
        stamp = str(window)[:13].replace("T", "-") if window else event.id[:12]
        kind = event.event_type or "report"
        path = inbox / f"kanban-report-{kind}-{stamp}-face.md"
        # Strip Worker-only instructions; Face only needs the outlook body.
        body_lines = []
        for line in event.text.splitlines():
            if line.startswith("Worker:"):
                break
            body_lines.append(line)
        body = "\n".join(body_lines).strip() or event.text.strip()
        try:
            path.write_text(
                f"# {kind} report\n\n{body}\n\n"
                f"_SE inbox_report after Worker nudge (event {event.id})._\n",
                encoding="utf-8",
            )
            logger.info("Inbox report written: %s", path)
        except OSError as exc:
            logger.warning("Inbox report write failed: %s", exc)

    async def _resolve_targets(self, event: Event, rule: RouteRule) -> list[SessionInfo]:
        """Resolve target sessions from explicit IDs, hints, and rules."""
        allowed = self._allowed_sources(event, rule)

        if event.targets:
            sessions = await self._registry.get_sessions_by_ids(event.targets)
            if not rule.broadcast:
                sessions = [s for s in sessions if s.source in allowed]
            return sessions[: rule.max_targets] if not rule.broadcast else sessions

        if event.preferred_target:
            session = await self._registry.get_session(event.preferred_target)
            if session is not None:
                if session.source not in allowed:
                    logger.warning(
                        "Event %s preferred_target %s (source=%s) not in allowed %s — re-resolving",
                        event.id,
                        event.preferred_target,
                        session.source,
                        allowed,
                    )
                elif session.active:
                    return [session]
                else:
                    resolved = await self._registry.find_session_for_source(session.source)
                    if resolved is not None and resolved.source in allowed:
                        if resolved.id != session.id:
                            logger.info(
                                "Event %s preferred_target %s is not the active route; using %s",
                                event.id,
                                session.id,
                                resolved.id,
                            )
                        return [resolved]
                    logger.warning(
                        "Event %s preferred_target %s inactive and no active %s session — re-resolving",
                        event.id,
                        event.preferred_target,
                        session.source,
                    )

        sessions = await self._registry.find_sessions_for_sources(
            allowed,
            max_targets=rule.max_targets,
            broadcast=rule.broadcast,
        )
        return sessions
