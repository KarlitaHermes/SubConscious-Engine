# Kanban + SE simplification (deferred)

Status: **parked** — revisit later. Not implemented yet.

## Scope (locked)

**Only add** SE’s ability to talk to Kanban via CLI (`hermes kanban create|schedule|unblock|list|show|notify-subscribe`).

**Do not** remove or redesign existing SE behavior for v1:

- Keep inject, idle, weather, inbox watcher, preferred_window, acks, notify gate, routing — as they are.
- Context return for Kanban work prefers **worker → `COMMS/Inbox/` → existing inbox → inject** (no new delivery path required beyond a report contract).
- OOB Kanban notify is optional, not a replacement for session inject.

```mermaid
flowchart LR
  seExisting[Existing_SE] --> tg[Telegram_inject]
  seNew[New_Kanban_CLI_client] --> kb[hermes_kanban]
  kb -->|inbox_report| inbox[COMMS_Inbox]
  inbox --> seExisting
```

## Hard constraint

SE never opens `kanban.db`. Subprocess CLI only (dashboard HTTP later only if CLI is insufficient).

## Target flow (when wired)

1. SE sensor (or config rule) decides to start work → CLI create/unblock card.
2. Kanban worker runs; writes report under `COMMS/Inbox/` (agreed prefix); completes.
3. Existing SE inbox path injects into Telegram session (context preserved).

Existing Telegram decision nudges / maintenance injects can keep running until we opt specific workflows onto Kanban triggers — additive, not a big-bang cutover.

## Thin spike (when we return)

1. Add thin `src/delivery/kanban.py` (async subprocess wrapper + tests).
2. Config knobs: hermes binary path, optional default assignee/board, telegram chat_id only if using notify-subscribe.
3. One entry/rule or scripted hook that creates a card (prove CLI from SE).
4. Document inbox report prefix for workers (`kanban-report-*.md` or similar).
5. Leave all current sources/router/inject paths unchanged.

## Non-goals for v1

- Removing inject or Adapter client
- Replacing idle/weather with Kanban
- Opening `kanban.db`
- Mandatory cutover of all workflows

## Checklist when resuming

- [ ] `src/delivery/kanban.py` CLI wrapper + unit tests (mocked subprocess)
- [ ] Minimal config for kanban CLI
- [ ] One optional trigger path (feature-flagged / disabled by default)
- [ ] Inbox report filename contract in docs
- [ ] No regressions to existing inject/inbox/idle tests
