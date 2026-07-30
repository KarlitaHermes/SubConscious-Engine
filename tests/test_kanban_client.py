"""Tests for Hermes Kanban CLI client (mocked subprocess)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.delivery.kanban import KanbanClient


def _mock_proc(*, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_create_builds_argv_and_parses_json(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _mock_proc(stdout=json.dumps({"task_id": "t_abc"}).encode())
    create_exec = AsyncMock(return_value=proc)
    monkeypatch.setattr(
        "src.delivery.kanban.asyncio.create_subprocess_exec",
        create_exec,
    )

    client = KanbanClient(hermes_bin="/usr/bin/hermes", board="default")
    result = await client.create(
        "night maintenance",
        body="do one task",
        assignee="ops",
        workspace="dir:/tmp/vault",
        idempotency_key="se-maint-1",
        triage=True,
    )

    assert result.ok is True
    assert result.data == {"task_id": "t_abc"}
    argv = list(create_exec.await_args.args)
    assert argv[:4] == ["/usr/bin/hermes", "kanban", "--board", "default"]
    assert argv[4:6] == ["create", "night maintenance"]
    assert "--body" in argv and "do one task" in argv
    assert "--assignee" in argv and "ops" in argv
    assert "--workspace" in argv and "dir:/tmp/vault" in argv
    assert "--idempotency-key" in argv and "se-maint-1" in argv
    assert "--triage" in argv
    assert "--json" in argv


@pytest.mark.asyncio
async def test_run_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_a, **_k):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(
        "src.delivery.kanban.asyncio.create_subprocess_exec",
        _boom,
    )
    client = KanbanClient(hermes_bin="no-such-hermes")
    result = await client.run("list", "--json")
    assert result.ok is False
    assert result.returncode == 127
    assert "not found" in (result.error or "")


@pytest.mark.asyncio
async def test_notify_subscribe_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _mock_proc(stdout=b"ok\n")
    create_exec = AsyncMock(return_value=proc)
    monkeypatch.setattr(
        "src.delivery.kanban.asyncio.create_subprocess_exec",
        create_exec,
    )
    client = KanbanClient()
    result = await client.notify_subscribe(
        "t_1",
        platform="telegram",
        chat_id="112072229",
    )
    assert result.ok is True
    argv = list(create_exec.await_args.args)
    assert argv == [
        "hermes",
        "kanban",
        "notify-subscribe",
        "t_1",
        "--platform",
        "telegram",
        "--chat-id",
        "112072229",
    ]


@pytest.mark.asyncio
async def test_schedule_and_unblock(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _mock_proc()
    create_exec = AsyncMock(return_value=proc)
    monkeypatch.setattr(
        "src.delivery.kanban.asyncio.create_subprocess_exec",
        create_exec,
    )
    client = KanbanClient()
    assert (await client.schedule("t_1", "overnight")).ok
    assert (await client.unblock("t_1", reason="window open")).ok
    calls = [list(c.args) for c in create_exec.await_args_list]
    assert calls[0][2:] == ["schedule", "t_1", "overnight"]
    assert calls[1][2:] == ["unblock", "t_1", "--reason", "window open"]
