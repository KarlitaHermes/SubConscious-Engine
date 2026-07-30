# Kanban + SubConscious Engine (Hermes guide)

How **Hermes** creates Kanban work that returns context into the Telegram session via **SE inbox**. This is the preferred path for User-requested tasks.

**Related:** `docs/CRON-AND-INBOX.md` (inbox prefixes), `docs/PLAN-KANBAN-SE.md` (SE optional CLI client), skill `hermes/kanban-se-bridge/`.

---

## Roles (locked)

| Who | Owns |
|-----|------|
| **Hermes (Agent)** | Create the Kanban card, workspace, assignee, body/contract, optional OOB notify |
| **Kanban worker** | Do the work; **must** write `kanban-report-*.md` to vault Inbox before complete |
| **SubConscious Engine** | Watch Inbox → classify → inject into active session (context return) |

**Do not** ask SE to create the card for User-initiated Telegram tasks. SE’s optional `KanbanClient` is only for future sensor-originated work (no Hermes chat turn).

```
User asks Hermes (Telegram)
    → Hermes: hermes kanban create … (full contract)
        ↓
Kanban worker runs
    → writes COMMS/Inbox/kanban-report-*.md
        ↓
SE inbox watcher (~30s)
    → event_type inbox_notify → inject (delivery: queue)
        ↓
Hermes session: [SUBCONSCIOUS] New inbox file: kanban-report-…
    → ack in_progress → summarize / file → ack done
```

OOB `notify-subscribe` (Telegram ping) is **optional** and does **not** replace the inbox report. Session context comes from SE inject.

---

## Prerequisites (SE)

Inbox entry point must be enabled (already true on working deployments):

```yaml
entry_points:
  - id: inbox
    type: directory
    enabled: true
    path: ~/path/to/your/obsidian-vault/COMMS/Inbox
    poll_interval_seconds: 30
    handle:
      handler: inbox
      default_event_type: inbox_item
      default_priority: 0

routing:
  rules:
    - name: inbox_notify
      match:
        event_type: inbox_notify
        entry_point: inbox
      deliver:
        target_sources: [telegram]
        max_targets: 1
        priority: 30
```

Full shape: `examples/working-deployment/engine-config.production.yaml`.

SE `kanban:` block may stay `enabled: false` for this Hermes-creates path — SE does not need to create cards.

---

## Hermes: create a card that nudges SE on completion

When the User asks for work that should come **back into this chat** after a Kanban worker finishes:

### 1. Create the task (CLI)

Prefer tilde / relative workspace — Hermes expands `~/…`:

```bash
hermes kanban create "[short title]" \
  --body "$(cat <<'EOF'
## Goal
<what to do>

## SE context return (required)
When finished, BEFORE marking the task complete, write a markdown report to:

  COMMS/Inbox/kanban-report-<task_id_or_slug>-YYYY-MM-DD.md

Use this shape:

---
source: kanban
task_id: <TASK_ID>
priority: high
---
# Kanban report: <title>

<summary for the main Hermes session>

## Details
<what changed / findings / next steps>

Then mark the Kanban task complete.
EOF
)" \
  --workspace "dir:~/path/to/your-obsidian-vault" \
  --assignee default \
  --idempotency-key "hermes-<stable-slug>" \
  --json
```

Notes:

- `--workspace dir:~/…` is preferred over absolute `/home/…` paths.
- Put the **inbox report contract in the task body** so the worker cannot miss it.
- Use a stable `--idempotency-key` so retries do not duplicate cards.
- Capture `task_id` from `--json` output for the report filename and optional notify.

### 2. Optional OOB ping

Subscribe the User’s Telegram **chat_id** (stable platform id — **not** Hermes `session_id`):

```bash
hermes kanban notify-subscribe <TASK_ID> \
  --platform telegram \
  --chat-id "<TELEGRAM_CHAT_ID>"
```

Configure chat id locally; never commit real ids to git.

### 3. Do nothing else for SE

Do not call SE APIs to “register” the task. The report file in Inbox **is** the trigger.

---

## Worker contract (must follow)

1. Do the assigned work under the task workspace.
2. Write `COMMS/Inbox/kanban-report-<slug>-YYYY-MM-DD.md` (prefix **exact**: `kanban-report-`).
3. Then complete / `kanban_complete` the task.

Filename prefix drives SE disposition → `inbox_notify` (see `src/checks/inbox.py`).

Suggested vault filing after SE inject: `Projects/Inbox-Processed/` (agent-side, via inbox curator).

---

## Hermes: when the SE nudge arrives

Inject looks like other inbox notifies:

- Prompt: `[SUBCONSCIOUS] New inbox file: kanban-report-….md`
- `event_type`: `inbox_notify`
- `cooldown_key`: `inbox:kanban-report-….md`

Procedure (same as other notify inbox files):

1. `ack-engine.sh inbox:FILENAME in_progress`
2. Read the report; fold summary into session context; notify User if useful
3. File under `Projects/Inbox-Processed/` when appropriate
4. `ack-engine.sh inbox:FILENAME done --minutes 60`

Skills: `hermes/subconscious-engine-nudges/`, `hermes/inbox-digest-curator/`, `hermes/kanban-se-bridge/`.

---

## Smoke test (CLI → Inbox → SE)

```bash
# 1) Create a tiny echo card (adjust vault path)
hermes kanban create "[SE TEST] Inbox echo report" \
  --body "Write COMMS/Inbox/kanban-report-se-test-YYYY-MM-DD.md then complete." \
  --workspace "dir:~/path/to/your-obsidian-vault" \
  --assignee default \
  --idempotency-key "se-test-inbox-echo" \
  --json

# 2) After worker finishes, confirm file exists
ls ~/path/to/your-obsidian-vault/COMMS/Inbox/kanban-report-*.md

# 3) Within ~30s SE should log inject
journalctl -u subconscious-engine -n 30 --no-pager | grep -E 'kanban-report|inbox_notify'
```

Expect: `Inbox event published for kanban-report-… (notify)` then `type=inbox_notify delivered` and later `Agent ack done for cooldown_key=inbox:kanban-report-…`.

---

## Anti-patterns

- SE creating User-requested Telegram tasks (Hermes owns create)
- Completing Kanban without writing `kanban-report-*.md` (no session context)
- Relying only on OOB notify for context return
- Using Hermes `session_id` as `notify-subscribe --chat-id` (use Telegram chat id)
- Opening `kanban.db` from SE or scripts (CLI only)
- Committing live chat ids, session ids, or vault home paths into this repo
