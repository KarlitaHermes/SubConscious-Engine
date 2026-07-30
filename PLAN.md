# SubConscious Engine — Project Plan

## Vision

A persistent daemon alongside Hermes Gateway that injects “subconscious” events into active sessions: idle maintenance, research, vault/inbox signals, weather, and custom drops — without modifying gateway code.

## What it does

1. Runs as a standalone systemd service
2. Ingests events from configured **entry points** (idle, file drop, inbound REST, outbound HTTP poll, vault inbox/rules)
3. Gates noise (cooldown, in-progress, budget, rules) via **NotifyGate**
4. Routes to session(s) and injects via SubConscious Adapter (`delivery: queue`)
5. Persists cooldowns, acks, and dedupe in its own YAML state file

## What it does not do

- Does **not** modify Hermes Gateway source
- Does **not** talk to gateway internal APIs for inject (adapter only)
- Does **not** manage platform adapters (adapter’s job)
- Does **not** store agent conversation history

## Architecture (current)

```
┌────────────────────── SubConscious Engine ──────────────────────┐
│                                                                  │
│  entry_points (sources) ──▶ EventBus ──▶ NotifyGate ──▶ Router   │
│       │                                              │           │
│       └──────── state.yaml ◀─────────────────────────┘           │
│                                                                  │
│  HTTP out: Adapter GET /sessions + POST /inject                  │
│  HTTP in:  engine :8770  /health /events /ack                    │
│  Idle:     Gateway REST for last human activity                  │
└──────────────────────────────────────────────────────────────────┘
```

See `ARCHITECTURE.md` for module detail.

## Technology

| Piece | Choice |
|-------|--------|
| Language | Python 3.11+ |
| HTTP | aiohttp |
| Config / state | YAML |
| Service | systemd |
| Logging | Rotating file under `~/.hermes/logs/` |

Dependencies: **aiohttp**, **pyyaml** (plus pytest for dev).

## Project structure

```
SubConscious-Engine/
├── config.yaml.example
├── config.test.yaml
├── pyproject.toml
├── requirements.txt
├── ARCHITECTURE.md
├── CONFIG.md
├── README-AGENT.md
├── TODO.md
├── docs/
│   └── CRON-AND-INBOX.md
├── examples/
│   └── working-deployment/     # sanitized production-shaped configs
├── hermes/                     # installable Hermes skills
├── systemd/
│   └── subconscious-engine.service
├── scripts/
│   └── install.sh
├── src/
│   ├── __main__.py             # python -m src
│   ├── app.py                  # orchestration
│   ├── state.py
│   ├── notify_gate.py
│   ├── config/
│   ├── events/
│   ├── router/
│   ├── delivery/
│   ├── sources/
│   ├── checks/
│   └── signals/
└── tests/                      # pytest, mocked HTTP
```

## Status

**Shipped (v1 event router):** idle + maintenance/research alternation, pending-decisions wake nudge, file drop, inbound REST + ack, http_poll (including Open-Meteo), vault inbox/rules sources, routing rules, notify gate, nudge budget, queue delivery, **preferred_window** (soft schedule → park or ASAP).

**Deferred:** CLI session inject (adapter Platform enum) — see `TODO.md`. Prefer `telegram` as `idle.target_source`.

**Parked (later):** Kanban as work engine, SE nudges via `hermes kanban` CLI only — see `docs/PLAN-KANBAN-SE.md`.

## Configuration

See `CONFIG.md`. Production-shaped examples: `examples/WORKING-DEPLOYMENT.md`.

## Coding standards

See `CODING_STANDARD.md`. Lessons from earlier automation: `LESSONS_LEARNED.md`.
