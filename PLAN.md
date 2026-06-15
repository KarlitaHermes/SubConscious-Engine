# SubConscious Engine — Project Plan

## Vision
A persistent, autonomous engine that monitors the Hermes Gateway and injects "subconscious" events into active sessions. The engine runs alongside the gateway, detects idle periods, and triggers maintenance tasks, research, or other out-of-band activities.

## What It Does
1. Runs as a standalone daemon (systemd service) alongside Hermes Gateway
2. Monitors gateway session activity via the Gateway REST API
3. Detects idle periods (no human activity for N minutes)
4. Injects maintenance prompts into the active user session via SubConscious Adapter
5. Manages its own state, cooldowns, and task scheduling

## What It Does NOT Do
- Does NOT modify the Hermes Gateway code
- Does NOT directly access the gateway's internal APIs
- Does NOT manage platform adapters (that's SubConscious Adapter's job)
- Does NOT store agent responses or conversation history

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SubConscious Engine                    │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  Idle Engine  │  │  Task Queue  │  │   Scheduler   │  │
│  │  (detects     │  │  (what to    │  │  (when to     │  │
│  │   idle time)  │  │   execute)   │  │   trigger)    │  │
│  └──────┬───────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                 │                   │          │
│         └────────────┬────┘───────────────────┘          │
│                      ▼                                    │
│              ┌──────────────┐                            │
│              │  App (main)  │                            │
│              │  (event loop)│                            │
│              └──────┬───────┘                            │
│                     │                                     │
│                     ▼ HTTP                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │         SubConscious Adapter (port 8769)          │   │
│  │         POST /inject → Gateway → User            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Technology Choices
- **Language:** Python 3.11+
- **HTTP Client:** aiohttp (already in gateway venv)
- **Config:** YAML file (`~/.hermes/subconscious-engine/config.yaml`)
- **State:** Simple YAML/JSON state file (no SQLite)
- **Service:** systemd unit file
- **Logging:** Python logging to `~/.hermes/logs/subconscious-engine.log`

## Project Structure

```
subconscious-engine/
├── config.yaml                 # Main configuration
├── config.yaml.example         # Example config with all options
├── requirements.txt            # Python dependencies (minimal)
├── setup.sh                    # Install script
├── systemd/
│   └── subconscious-engine.service  # systemd unit file
├── src/
│   ├── __init__.py
│   ├── __main__.py             # Entry point
│   ├── app.py                  # Main application loop
│   ├── config.py               # Configuration loader
│   ├── idle_engine.py          # Idle detection logic
│   ├── delivery.py             # SubConscious HTTP client
│   ├── state.py                # State management (cooldowns, timestamps)
│   └── signals/
│       ├── __init__.py
│       └── session.py          # Session monitoring signals
├── tests/
│   ├── __init__.py
│   ├── test_idle_engine.py
│   ├── test_delivery.py
│   └── test_state.py
└── scripts/
    └── install.sh              # Installation helper
```

## Dependencies (Minimal)
- `aiohttp` — HTTP client for SubConscious Adapter API
- `pyyaml` — Config file parsing

That's it. No heavy frameworks.

## Configuration Reference

See `CONFIG.md` for full configuration options.

## Coding Standards

See `CODING_STANDARD.md` for detailed coding conventions.

## Lessons Learned from Old Orchestrator

See `LESSONS_LEARNED.md` for pitfalls to avoid.
