# Kanban + SE simplification

Status: **CLI client shipped** (additive). Triggers still optional / unused by default.

Revert checkpoint before this work: `611d7f5` on `main`.

## Scope (locked)

**Added:** SE can talk to Kanban via CLI (`src/delivery/kanban.py` → `hermes kanban …`).

**Unchanged:** inject, idle, weather, inbox watcher, preferred_window, acks, notify gate, routing.

**Context return:** worker writes `COMMS/Inbox/kanban-report-*.md` → existing inbox → inject (see `docs/CRON-AND-INBOX.md`).

## Config

```yaml
kanban:
  enabled: false          # must stay false until a trigger is wired
  hermes_bin: hermes
  board: ""
  default_assignee: ""
  timeout_seconds: 60
  notify_platform: ""     # optional OOB
  notify_chat_id: ""      # Telegram chat_id, not session_id
```

Usage from code (when `enabled`):

```python
from src.delivery.kanban import KanbanClient

client = KanbanClient(
    hermes_bin=config.kanban.hermes_bin,
    board=config.kanban.board,
    timeout_seconds=config.kanban.timeout_seconds,
)
result = await client.create("title", assignee="ops", idempotency_key="se-…", json_output=True)
```

## Hard constraint

Never open `kanban.db`. Subprocess CLI only.

## Still TODO (when wiring a trigger)

- [ ] Optional sensor/rule that calls `KanbanClient` (feature-flagged)
- [ ] Worker skill/docs: must write `kanban-report-*.md` then complete
- [ ] Optional `notify-subscribe` after create when `notify_chat_id` set
