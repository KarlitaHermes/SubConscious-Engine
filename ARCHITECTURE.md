# SubConscious Engine — Architecture

## Overview
The engine is a simple async daemon that:
1. Polls the gateway for active sessions
2. Checks if the target session is idle
3. If idle, injects a maintenance prompt via SubConscious Adapter
4. Waits for cooldown, repeats

## Main Loop

```
┌─────────────────────────────────────────────────────────┐
│                      Main Loop                           │
│                                                          │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐     │
│  │   Sleep    │───▶│   Poll     │───▶│   Check    │     │
│  │  (60s)     │    │  Sessions  │    │   Idle     │     │
│  └────────────┘    └────────────┘    └─────┬──────┘     │
│       ▲                                    │            │
│       │                                    ▼            │
│       │              ┌────────────┐    ┌────────────┐   │
│       │              │  Update    │◀───│  Inject    │   │
│       │              │   State    │    │  Prompt    │   │
│       │              └────────────┘    └────────────┘   │
│       │                                                 │
│       └─────────────────────────────────────────────────┘
│                    (cooldown wait)                        │
└─────────────────────────────────────────────────────────┘
```

## Module Responsibilities

### app.py — Main Application
- Loads config
- Initializes all modules
- Runs the main event loop
- Handles graceful shutdown (SIGTERM, SIGINT)
- NO business logic here, just orchestration

### config.py — Configuration
- Loads `config.yaml`
- Validates required fields
- Provides typed config objects
- Loads `API_SERVER_KEY` from `~/.hermes/.env`

### idle_engine.py — Idle Detection
- Queries gateway for session activity
- Compares last activity timestamp against threshold
- Returns True/False for "should trigger"
- Pure logic, no side effects

### delivery.py — SubConscious HTTP Client
- `find_target_session()` — GET /sessions, pick best match
- `inject_prompt(session_id, prompt)` — POST /inject
- Handles HTTP errors, timeouts
- No retry logic (the main loop handles retries via cooldown)

### state.py — State Management
- Reads/writes state YAML file
- Tracks: last_trigger, trigger_count, last_target, last_status
- Thread-safe file operations
- Simple dict-like interface

### signals/session.py — Session Monitoring
- Queries gateway for session info
- Extracts last activity timestamp
- Pure data, no logic

## Data Flow

```
config.yaml ──▶ config.py ──▶ app.py
                                    │
gateway API ◀── delivery.py ◀─────┤
                                    │
state.yaml ◀─── state.py ◀─────────┤
                                    │
idle check ◀── idle_engine.py ◀───┤
                   ▲               │
                   └── signals/ ───┘
```

## Error Strategy
- **HTTP errors:** Log and skip (retry on next loop iteration)
- **Config errors:** Fail fast on startup
- **State errors:** Log warning, use defaults
- **Unknown errors:** Log with traceback, continue loop

## Shutdown Handling
- SIGTERM/SIGINT sets `_running = False`
- Current iteration completes before exit
- State is saved before exit
- Max 5 seconds to shut down gracefully
