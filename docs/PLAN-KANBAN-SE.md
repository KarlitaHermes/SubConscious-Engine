# Kanban + SE simplification

Status: **Hermes-creates + inbox return — done.** Optional SE→Kanban create remains parked.

Canonical Hermes howto: **`docs/KANBAN-AND-SE.md`**  
Skill: **`hermes/kanban-se-bridge/`**

Revert checkpoint before Kanban client work: `611d7f5` on `main`.

## Roles (locked)

| Who | Role |
|-----|------|
| Hermes | Create card + contract for User Telegram tasks |
| Kanban worker | Work + write `kanban-report-*.md` to Inbox |
| SE | Inbox → inject (context return). Does **not** create User cards |

## Shipped

- SE CLI client `src/delivery/kanban.py` (subprocess only; never open `kanban.db`) — available if a future **sensor** trigger needs SE-originated cards
- Inbox prefix `kanban-report-` → `inbox_notify` (`src/checks/inbox.py`)
- Docs + Hermes skill for create → report → inject

## Config (optional SE client)

```yaml
kanban:
  enabled: false          # leave false for Hermes-creates path
  hermes_bin: hermes
  board: ""
  default_assignee: ""
  timeout_seconds: 60
  notify_platform: ""     # optional OOB
  notify_chat_id: ""      # Telegram chat_id, not session_id
```

## Hard constraint

Never open `kanban.db`. Subprocess CLI only.

## Parked (optional later)

- [ ] Sensor/rule that calls `KanbanClient` (feature-flagged) when there is no Hermes chat turn
- [ ] Auto `notify-subscribe` after SE-originated create when `notify_chat_id` set
