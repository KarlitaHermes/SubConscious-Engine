# SubConscious Engine — Agent Setup Guide

This document tells an automated agent (or a human following exact steps) how to install, configure, and start **SubConscious Engine**.

Read this entire file before changing anything. Do not assume services, paths, or credentials exist unless you have verified them on the machine you are working on.

---

## 1. What this program does

SubConscious Engine is a **long-running Python daemon**. It:

1. Watches configured **entry points** (directories, HTTP API, idle poller).
2. Turns what it finds into **events**.
3. **Routes** each event using rules in the config file.
4. **Injects** a message into one or more Hermes sessions via the **SubConscious Adapter**.

It does **not** run inside the Hermes Gateway process. It is a separate program that talks to external HTTP services.

---

## 2. Prerequisites (verify before proceeding)

Complete this checklist on the host where you will run the engine.

### 2.1 Software

| Requirement | Minimum | How to check |
|-------------|---------|----------------|
| Python | 3.11+ | `python3 --version` |
| pip | any recent | `python3 -m pip --version` |
| git | any | `git --version` (only if cloning) |

### 2.2 External services (must be running)

The engine will start without these, but **injection and idle detection will fail** if they are down.

| Service | Default URL | Purpose |
|---------|-------------|---------|
| **Hermes Gateway** | `http://127.0.0.1:8642` | Session activity / idle detection |
| **SubConscious Adapter** | `http://127.0.0.1:8769` | List sessions, inject messages |

Verify they respond (from the same machine):

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8642/
curl -s http://127.0.0.1:8769/sessions
```

- Gateway may return various status codes depending on route; it should not be "connection refused".
- Adapter `/sessions` should return JSON (possibly an empty list), not connection refused.

### 2.3 API key

The engine needs the Gateway API key (`API_SERVER_KEY`).

**Expected location:** `~/.hermes/.env`

**Expected line format:**

```
API_SERVER_KEY=your-secret-key-here
```

If `gateway.api_key` in the config file is empty (`""`), the engine **automatically reads** this value from `~/.hermes/.env` at startup.

You can also set it directly in the config under `gateway.api_key`.

### 2.4 Target sessions

Routing delivers to sessions whose `source` matches `target_sources` in routing rules (commonly `telegram`).

**Important:** CLI session injection is currently broken in the adapter. Do **not** rely on `fallback_sources: ["cli"]` until that is fixed (see `TODO.md`). Use `telegram` as `idle.target_source`.

---

## 3. Get the code and install dependencies

### 3.1 Repository location

This guide assumes the repository is checked out at a path like:

```
/home/hermes/workspace/subconscious-engine
```

If your path differs, substitute it in every command below.

### 3.2 Create a virtual environment (recommended)

Run from the repository root:

```bash
cd /home/hermes/workspace/subconscious-engine
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Minimum install (without dev/test tools):

```bash
python -m pip install aiohttp pyyaml
```

### 3.3 Confirm the package imports

```bash
cd /home/hermes/workspace/subconscious-engine
python -c "from src.config import load_config; print('ok')"
```

Expected output: `ok`

---

## 4. Create the config file

### 4.1 Where the config file lives

The engine looks for config in this order:

1. Path passed on the command line: `--config /path/to/config.yaml`
2. Environment variable: `SUBCONSCIOUS_CONFIG=/path/to/config.yaml`
3. Default path: `~/.hermes/subconscious-engine/config.yaml`

**For production / normal use**, create the default file:

```bash
mkdir -p ~/.hermes/subconscious-engine
cp /home/hermes/workspace/subconscious-engine/config.yaml.example ~/.hermes/subconscious-engine/config.yaml
```

**For safe local testing**, use the bundled test profile instead (idle disabled, separate ports/paths):

```bash
# No copy needed — reference the file in the repo directly
# /home/hermes/workspace/subconscious-engine/config.test.yaml
```

### 4.2 Edit the config

Open the config file in an editor and adjust values for this machine. At minimum, verify:

| Key | What to set |
|-----|-------------|
| `idle.vault_root` | Absolute or `~` path to the Obsidian vault on this host |
| `gateway.url` | Gateway base URL if not `http://127.0.0.1:8642` |
| `adapter.url` | Adapter base URL if not `http://127.0.0.1:8769` |
| `entry_points[].path` | Directories that exist or should be created |
| `entry_points[].enabled` | `false` for anything you do not want active yet |

Paths support `~` (home directory). They are expanded to absolute paths at load time.

---

## 5. Config file structure (section by section)

The config is a single YAML file. Below is what each top-level section means and what an agent should set.

### 5.1 `gateway`

```yaml
gateway:
  url: "http://127.0.0.1:8642"
  api_key: ""
```

| Field | Meaning |
|-------|---------|
| `url` | Hermes Gateway HTTP API base URL. Overridden by env `GATEWAY_URL` if set. |
| `api_key` | Bearer token for Gateway. Leave empty to auto-load from `~/.hermes/.env`. |

Used for: detecting human activity on sessions (idle source).

### 5.2 `adapter`

```yaml
adapter:
  url: "http://127.0.0.1:8769"
```

| Field | Meaning |
|-------|---------|
| `url` | SubConscious Adapter base URL. Overridden by env `SUBCONSCIOUS_URL` if set. |

Used for: listing sessions and injecting messages.

### 5.3 `idle`

```yaml
idle:
  threshold_minutes: 30
  cooldown_minutes: 60
  target_source: "telegram"
  fallback_sources: ["cli"]
  vault_root: "~/Documents/Obsidian Vault"
  wake_grace_minutes: 10
```

| Field | Meaning |
|-------|---------|
| `threshold_minutes` | No human activity for this long → session considered idle. |
| `cooldown_minutes` | Minimum minutes between idle-triggered injections (also default for routing cooldowns). |
| `target_source` | Preferred session source for idle events (use `telegram`). |
| `fallback_sources` | Tried if primary source has no session. CLI is broken; prefer `[]`. |
| `vault_root` | Obsidian vault path; used to build maintenance/research/decision prompts. |
| `wake_grace_minutes` | After idle, if human activity returns within this window, emit pending-decisions nudge. |

This block configures the **idle entry point** behaviour. It does not enable/disable the idle entry point — that is controlled under `entry_points`.

### 5.4 `poll_interval_seconds`

```yaml
poll_interval_seconds: 60
```

Seconds between **idle entry point** evaluation cycles. Only affects the idle poller, not directory or HTTP entry points.

### 5.5 `entry_points`

List of ingress points. Each item has:

```yaml
entry_points:
  - id: events_drop          # unique name — referenced in routing rules
    type: directory          # directory | http | idle
    enabled: true
    path: "~/.hermes/subconscious-engine/events"
    poll_interval_seconds: 5
    archive_dir: "~/.hermes/subconscious-engine/events/processed"
    handle:
      parser: auto
      handler: event_file    # event_file | inbox | vault_rules
      default_event_type: custom
      default_priority: 0
```

#### Entry point types

| `type` | What it does |
|--------|----------------|
| `directory` | Polls a folder. Handler decides how files are interpreted. |
| `http` | Starts an HTTP server (default `127.0.0.1:8770`) with `POST /events`. |
| `idle` | Polls session activity and emits maintenance/research/decision events. |

#### Directory handlers (`handle.handler`)

| Handler | Watches | Emits |
|---------|---------|-------|
| `event_file` | `.json`, `.yaml`, `.yml`, `.txt` drop files | One event per file; file moved to `archive_dir` after publish |
| `inbox` | `*.md` in inbox directory | One event per new inbox markdown file |
| `vault_rules` | Evaluates `rules.md` on interval | Events when vault rules match |

**HTTP entry point** example:

```yaml
  - id: api
    type: http
    enabled: true
    host: "127.0.0.1"
    port: 8770
    api_key: ""              # optional — if set, clients must send Bearer token
    handle:
      default_event_type: custom
```

**Idle entry point** example:

```yaml
  - id: idle
    type: idle
    enabled: true            # set false to disable idle injections entirely
```

Set `enabled: false` on any entry point you do not want started.

### 5.6 `routing`

Defines how events are matched and where they are delivered.

```yaml
routing:
  rules:
    - name: maintenance
      match:
        event_type: maintenance
        entry_point: idle       # optional — omit to match any entry point
        min_event_priority: 0   # optional
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        cooldown_minutes: 60
        priority: 10
        broadcast: false
        active_hours: []        # optional — list of hours 0-23
        active_days: []         # optional — 0=Mon .. 6=Sun
```

| `match` field | Meaning |
|---------------|---------|
| `event_type` | Event type string, or `"*"` for any |
| `entry_point` | Only match events from this entry point `id` |
| `min_event_priority` | Event `priority` must be >= this value |

| `deliver` field | Meaning |
|-----------------|---------|
| `target_sources` | Session sources to inject into (e.g. `telegram`) |
| `max_targets` | Max sessions to inject (unless `broadcast: true`) |
| `cooldown_minutes` | Per-event cooldown before same type fires again |
| `priority` | Higher wins when multiple rules match |
| `broadcast` | If true, inject to all matching sessions |

**Legacy format** still works and is auto-migrated:

```yaml
sources:
  file: { enabled: true, directory: "...", ... }
  rest: { enabled: true, port: 8770, ... }
  idle: false

router:
  rules:
    - event_type: maintenance
      target_sources: ["telegram"]
```

Prefer `entry_points` + `routing` for new configs.

### 5.7 `logging`

```yaml
logging:
  level: "INFO"
  file: "~/.hermes/logs/subconscious-engine.log"
  max_bytes: 10485760
  backup_count: 3
```

Log file directory is created automatically. Levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

### 5.8 `state`

```yaml
state:
  file: "~/.hermes/subconscious-engine/state.yaml"
```

Persists cooldowns, idle counters, processed inbox files, rule last-run times. Do not delete while the engine is running.

---

## 6. Start the engine

All commands assume you are in the repository root and (if used) the virtualenv is activated:

```bash
cd /home/hermes/workspace/subconscious-engine
source .venv/bin/activate   # if using venv
```

### 6.1 Production start (default config path)

```bash
python -m src
```

Equivalent to using `~/.hermes/subconscious-engine/config.yaml`.

### 6.2 Start with explicit config file

```bash
python -m src --config /path/to/config.yaml
```

Example — test profile (recommended for agents doing local verification):

```bash
python -m src --config /home/hermes/workspace/subconscious-engine/config.test.yaml
```

### 6.3 Start via environment variable

```bash
export SUBCONSCIOUS_CONFIG=/home/hermes/workspace/subconscious-engine/config.test.yaml
python -m src
```

### 6.4 Run in background (example)

```bash
nohup python -m src --config ~/.hermes/subconscious-engine/config.yaml \
  >> ~/.hermes/logs/subconscious-engine-stdout.log 2>&1 &
echo $!   # note the PID
```

Stop with `kill <PID>` or Ctrl+C if running in foreground.

### 6.5 Expected startup log lines

On success you should see log output similar to:

- `File event source events_drop watching ...`
- `REST event source api listening on 127.0.0.1:8770` (if HTTP enabled)
- `Idle event source started ...` (if idle entry point enabled)
- `SubConscious Engine started`

If config is missing:

```
Error: Config not found: /home/.../.hermes/subconscious-engine/config.yaml
```

Fix by creating the config (section 4).

---

## 7. Verify it is working

### 7.1 Health check (HTTP entry point)

If the `api` entry point is enabled on port 8770:

```bash
curl -s http://127.0.0.1:8770/health
```

Expected: `{"ok": true, "service": "subconscious-engine"}`

Test profile uses port **8771**:

```bash
curl -s http://127.0.0.1:8771/health
```

### 7.2 Send a test event via HTTP

**Warning:** Injected messages run the full agent in the target session. For live tests, use the test profile, a dedicated session, and clearly marked test text.

```bash
curl -s -X POST http://127.0.0.1:8771/events \
  -H "Content-Type: application/json" \
  -d '{
    "text": "[SUBCONSCIOUS ENGINE TEST] ping from agent setup",
    "event_type": "custom",
    "cooldown_key": "agent_setup_test"
  }'
```

Expected response: `{"ok": true, "event_id": "..."}` with HTTP status 202.

If `api_key` is set in config, add:

```bash
  -H "Authorization: Bearer YOUR_API_KEY"
```

### 7.3 Send a test event via file drop

With test profile, events directory is `~/.hermes/subconscious-engine/events-test`:

```bash
mkdir -p ~/.hermes/subconscious-engine/events-test
cat > ~/.hermes/subconscious-engine/events-test/test-event.json <<'EOF'
{
  "text": "[SUBCONSCIOUS ENGINE TEST] file drop ping",
  "event_type": "custom",
  "cooldown_key": "agent_file_test"
}
EOF
```

Within a few seconds (poll interval is 2s in test config), the file should move to `events-test/processed/` and an inject attempt should appear in logs.

### 7.4 Read logs

```bash
tail -f ~/.hermes/logs/subconscious-engine.log
# or for test profile:
tail -f ~/.hermes/logs/subconscious-engine-test.log
```

Look for: `Event <id> type=custom delivered 1/1` (success) or warnings about no targets / cooldown.

---

## 8. Environment variables (summary)

| Variable | Effect |
|----------|--------|
| `SUBCONSCIOUS_CONFIG` | Path to config YAML if `--config` not passed |
| `GATEWAY_URL` | Overrides `gateway.url` |
| `SUBCONSCIOUS_URL` | Overrides `adapter.url` |
| `API_SERVER_KEY` | In `~/.hermes/.env`; used when `gateway.api_key` is empty |

---

## 9. Safety rules for agents

1. **Do not enable idle** (`entry_points` id `idle` with `enabled: true`) during automated testing unless explicitly instructed. Idle triggers real maintenance/research prompts.
2. **Do not inject** into a user's main Telegram session without explicit approval.
3. **Use the test config** (`config.test.yaml`) for setup verification: idle off, port 8771, separate state file.
4. **Always set `cooldown_key`** on test events to avoid blocking future tests.
5. **Never put secrets** in git-tracked config files. Use `~/.hermes/.env` for `API_SERVER_KEY`.
6. Test message text should include `[SUBCONSCIOUS ENGINE TEST]` and must not reference maintenance task files or open-ended instructions.

---

## 10. Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `Config not found` | No config at default path | Run section 4.1 |
| `Connection refused` on inject | Adapter not running | Start SubConscious Adapter; check `adapter.url` |
| `No targets resolved` | No active telegram session | Ensure a session with `source: telegram` exists: `curl http://127.0.0.1:8769/sessions` |
| `Event in cooldown` | Recent delivery with same `cooldown_key` | Wait or use a new `cooldown_key`; check `state.yaml` |
| `Unauthorized` on POST /events | `api_key` set in config | Send `Authorization: Bearer <key>` header |
| CLI fallback fails | Known adapter bug | Remove `cli` from `fallback_sources`; use `telegram` only |
| Port already in use | Another process on 8770/8771 | Change `entry_points` HTTP `port` or stop the other process |

---

## 11. Quick reference — minimal path from zero to running

```bash
# 1. Install
cd /home/hermes/workspace/subconscious-engine
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"

# 2. Config (production)
mkdir -p ~/.hermes/subconscious-engine
cp config.yaml.example ~/.hermes/subconscious-engine/config.yaml
# Edit vault_root, paths, and disable idle/inbox/vault_rules until ready

# 3. Verify prerequisites
test -f ~/.hermes/.env && grep API_SERVER_KEY ~/.hermes/.env
curl -s http://127.0.0.1:8769/sessions | head

# 4. Start (foreground, test profile)
python -m src --config config.test.yaml

# 5. Verify (separate terminal)
curl -s http://127.0.0.1:8771/health
```

---

## 12. Related files in this repository

| File | Purpose |
|------|---------|
| `config.yaml.example` | Full production config template |
| `config.test.yaml` | Safe test profile (idle off) |
| `ARCHITECTURE.md` | Internal design overview |
| `CONFIG.md` | Shorter config reference (partially legacy) |
| `TODO.md` | Known limitations (CLI inject, testing rules) |

When instructions conflict, prefer this file for setup/start steps and `config.yaml.example` for the canonical config shape.
