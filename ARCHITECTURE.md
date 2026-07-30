# SubConscious Engine — Architecture

## Overview

An async daemon that turns **entry points** into **events**, gates them, routes them to Hermes sessions, and injects via the SubConscious Adapter.

```
entry points → EventBus → NotifyGate → Router → Adapter POST /inject
                    ↑                        ↓
              (sources publish)         StateManager (YAML)
```

It does **not** modify Hermes Gateway code. Session list and inject go through the adapter (`GET /sessions`, `POST /inject`). Idle activity uses the Gateway REST API.

## Data flow

```
config.yaml ──▶ config/ ──▶ app.py
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
               sources/    EventBus    NotifyGate
                    │          │          │
                    └────▶─────┴────▶─────┘
                               ▼
                            Router
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                ▼
        SessionRegistry   SubConsciousClient   state.yaml
         (adapter)         (adapter inject)
```

## Main loop (`app.py`)

1. Load config, open shared `aiohttp` session
2. Build delivery client, session registry, notify gate, router
3. Start each enabled entry point as an async task (publish to `EventBus`)
4. Consume bus events → `Router.handle` → log delivery counts
5. Flush `state.deferred` ~every 60s (preferred-window promote)
6. On SIGTERM/SIGINT: close bus, stop sources, cancel tasks, save state

Orchestration only — no business logic in `app.py`.

## Module responsibilities

### `config/` — Configuration

- Load `config.yaml` (`SUBCONSCIOUS_CONFIG` or `~/.hermes/subconscious-engine/config.yaml`)
- Typed models: gateway, adapter, idle, entry points, routing, logging, state
- Auto-load `API_SERVER_KEY` from `~/.hermes/.env` when `gateway.api_key` is empty
- Legacy `sources` / `router` blocks still migrate to `entry_points` / `routing`

### `events/` — Bus and models

- `Event` / `DeliveryResult` / `EventSourceKind`
- Priority queue bus (higher `priority` first; FIFO within same priority)

### `sources/` — Entry points

| Type | Module | Behavior |
|------|--------|----------|
| `directory` + `event_file` | `file_watcher.py` | Poll drop dir → archive |
| `directory` + `inbox` | `inbox_watcher.py` | Vault inbox classification |
| `directory` + `vault_rules` | `vault_rules.py` | Evaluate vault `rules.md` |
| `http` | `rest_server.py` | `GET /health`, `POST /events`, `POST /ack` |
| `http_poll` | `rest_poller.py` | Outbound fetch + dedupe (`open_meteo`, lists, …) |
| `idle` | `idle.py` | Idle / wake / pending-decisions nudges |

### `notify_gate.py` — Suppress before notify

Shared checks used at publish and/or deliver:

- No matching routing rule (time / priority / entry point / task_id)
- Poll item already seen
- Task `in_progress` for cooldown key
- Cooldown active
- Global nudge budget (`idle.nudge_budget_per_hour`)
- Preferred window wait → defer (park in state; flush promotes in-window or ASAP)

### `router/` — Target resolution and delivery

- Match routing rules (`rules.py`) on `event_type`, optional `entry_point`, optional `task_id`/`task`
- Prefer exact type over `*`, task-specific over generic, then higher rule priority
- Resolve sessions via registry (explicit IDs → preferred → source match)
- Skip `cron` / `subagent` / `api_server` sources
- Append `[engine-ack:key|in_progress,done]` when `cooldown_key` is set
- Record successful deliveries into state

### `delivery/` — Adapter HTTP

- `sessions.py` — list/filter active sessions
- `subconscious.py` — `POST /inject` with `delivery: "queue"` by default

### `state.py` — Persistence

YAML under `state.file`: cooldowns, deliveries, acks, `tasks_in_progress`, poll/file dedupe, idle period flags, active session tracking, nudge timestamps, and **`deferred`** (preferred-window park queue; preserves `task_id`). Atomic write via temp file + replace.

### `checks/` — Vault helpers and prompts

Scan vault for decisions/inbox/rules; build maintenance / research / pending-decisions prompt text for the idle source. `music_task.py` detects when daily music curation is due so idle can tag `task_id: music_curation`.

### `signals/session.py` — Activity

Gateway query for last human activity (idle detection input).

## Preferred window

Routing rules may set `deliver.preferred_window` (`hours`, `max_wait_hours`, `fallback: asap`):

1. Gate returns `DEFER_PREFERRED_WINDOW` when the next preferred hours start within `max_wait_hours`
2. Router parks the event in `state.deferred` (no inject, no cooldown yet)
3. App `_deferred_flush_loop` (~60s) promotes when inside the window or past `prefer_until` (ASAP)
4. If the next window is farther than `max_wait_hours`, deliver immediately (ASAP)

Hard `active_hours` / `active_days` still drop events (no park). See `CONFIG.md`.

## Ack protocol

Hermes acks via `POST /ack` on the inbound HTTP entry point (default `:8770`):

1. `in_progress` — blocks another nudge with the same `cooldown_key`
2. `done` — clears in-progress, starts cooldown

Stale `in_progress` expires after one cooldown window (minimum 60 minutes). Changing the active session for a source clears all in-progress locks.

## Error strategy

- **HTTP / inject errors:** Log, continue (next loop or next event)
- **Config errors:** Fail fast on startup
- **State errors:** Warn, use defaults
- **Unknown errors in consume/source loops:** Log with traceback, keep running

## Shutdown

- SIGTERM/SIGINT → `_running = False`, bus closed
- Sources stopped, tasks cancelled, HTTP closed, state saved
- Current consume iteration may finish before exit

## Related docs

- `CONFIG.md` — config reference
- `TODO.md` — deferred items (e.g. CLI inject)
- `examples/WORKING-DEPLOYMENT.md` — sanitized production shape
- `README-AGENT.md` — install and ops for agents
