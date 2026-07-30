"""Hermes Kanban CLI client — subprocess only, never opens kanban.db."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class KanbanResult:
    """Outcome of one hermes kanban CLI invocation."""

    ok: bool
    returncode: int
    stdout: str
    stderr: str
    data: Any = None
    error: Optional[str] = None


class KanbanClient:
    """Thin async wrapper around ``hermes kanban …`` (CLI only)."""

    def __init__(
        self,
        *,
        hermes_bin: str = "hermes",
        board: str = "",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._hermes_bin = hermes_bin
        self._board = board.strip()
        self._timeout = timeout_seconds

    def _base_argv(self) -> list[str]:
        argv = [self._hermes_bin, "kanban"]
        if self._board:
            argv.extend(["--board", self._board])
        return argv

    async def run(self, *args: str) -> KanbanResult:
        """Run ``hermes kanban`` with extra args."""
        argv = self._base_argv() + list(args)
        logger.debug("kanban CLI: %s", " ".join(argv))
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            msg = f"hermes binary not found: {self._hermes_bin}"
            logger.error(msg)
            return KanbanResult(ok=False, returncode=127, stdout="", stderr=msg, error=msg)

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            msg = f"kanban CLI timed out after {self._timeout}s"
            logger.error(msg)
            return KanbanResult(ok=False, returncode=-1, stdout="", stderr=msg, error=msg)

        stdout = stdout_b.decode("utf-8", errors="replace")
        stderr = stderr_b.decode("utf-8", errors="replace")
        code = int(proc.returncode or 0)
        data = None
        if "--json" in args:
            text = stdout.strip()
            if text:
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    msg = f"kanban CLI returned invalid JSON: {exc}"
                    logger.warning(msg)
                    return KanbanResult(
                        ok=False,
                        returncode=code,
                        stdout=stdout,
                        stderr=stderr,
                        error=msg,
                    )
        ok = code == 0
        error = None if ok else (stderr.strip() or stdout.strip() or f"exit {code}")
        if not ok:
            logger.warning("kanban CLI failed (%s): %s", code, error)
        return KanbanResult(
            ok=ok,
            returncode=code,
            stdout=stdout,
            stderr=stderr,
            data=data,
            error=error,
        )

    async def create(
        self,
        title: str,
        *,
        body: str = "",
        assignee: str = "",
        workspace: str = "",
        idempotency_key: str = "",
        triage: bool = False,
        json_output: bool = True,
    ) -> KanbanResult:
        """Create a task. Prefer ``json_output=True`` for machine use."""
        args: list[str] = ["create", title]
        if body:
            args.extend(["--body", body])
        if assignee:
            args.extend(["--assignee", assignee])
        if workspace:
            args.extend(["--workspace", workspace])
        if idempotency_key:
            args.extend(["--idempotency-key", idempotency_key])
        if triage:
            args.append("--triage")
        if json_output:
            args.append("--json")
        return await self.run(*args)

    async def schedule(self, task_id: str, reason: str = "") -> KanbanResult:
        """Park a task in scheduled status."""
        args = ["schedule", task_id]
        if reason:
            args.append(reason)
        return await self.run(*args)

    async def unblock(self, task_id: str, *, reason: str = "") -> KanbanResult:
        """Move blocked/scheduled task back toward ready/todo."""
        args = ["unblock", task_id]
        if reason:
            args.extend(["--reason", reason])
        return await self.run(*args)

    async def show(self, task_id: str, *, json_output: bool = True) -> KanbanResult:
        """Show one task."""
        args = ["show", task_id]
        if json_output:
            args.append("--json")
        return await self.run(*args)

    async def list_tasks(
        self,
        *,
        status: str = "",
        assignee: str = "",
        json_output: bool = True,
    ) -> KanbanResult:
        """List tasks, optionally filtered."""
        args = ["list"]
        if status:
            args.extend(["--status", status])
        if assignee:
            args.extend(["--assignee", assignee])
        if json_output:
            args.append("--json")
        return await self.run(*args)

    async def notify_subscribe(
        self,
        task_id: str,
        *,
        platform: str,
        chat_id: str,
        thread_id: str = "",
        user_id: str = "",
    ) -> KanbanResult:
        """Subscribe a gateway chat to terminal events for a task."""
        args = [
            "notify-subscribe",
            task_id,
            "--platform",
            platform,
            "--chat-id",
            chat_id,
        ]
        if thread_id:
            args.extend(["--thread-id", thread_id])
        if user_id:
            args.extend(["--user-id", user_id])
        return await self.run(*args)
