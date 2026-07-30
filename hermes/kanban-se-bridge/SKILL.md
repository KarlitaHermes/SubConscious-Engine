---
name: kanban-se-bridge
category: productivity
description: >
  Create Hermes Kanban tasks that return context via SubConscious Engine inbox
  (kanban-report-*.md → inject). Use when User work should come back into the
  Telegram session after a Kanban worker finishes.
---

# Kanban → SE context return

**Canonical howto:** `docs/KANBAN-AND-SE.md`

## Rule

- **Hermes creates** the Kanban card (title, body, workspace, assignee).
- **Worker writes** `COMMS/Inbox/kanban-report-*.md` before complete.
- **SE injects** that file into the session (`inbox_notify`). Do not ask SE to create the card for User-initiated Telegram tasks.

## When creating a card for session return

1. Put the inbox report contract in `--body` (see doc).
2. Prefer `--workspace dir:~/path/to/your-obsidian-vault` (tilde OK).
3. Use a stable `--idempotency-key`.
4. Optional: `hermes kanban notify-subscribe <id> --platform telegram --chat-id <TELEGRAM_CHAT_ID>` (chat id ≠ session id). OOB ping does **not** replace the report file.

## When SE injects `kanban-report-*`

Same as other `inbox_notify` files:

1. `ack-engine.sh inbox:FILENAME in_progress`
2. Summarize into session; notify User if useful; file to `Projects/Inbox-Processed/`
3. `ack-engine.sh inbox:FILENAME done --minutes 60`

Full ACK skill: `hermes/subconscious-engine-nudges/SKILL.md`.  
Inbox curator: `hermes/inbox-digest-curator/SKILL.md`.
