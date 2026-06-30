# SubConscious Engine — Agent Setup Guide

This document tells an automated agent (or a human following exact steps) how to install, configure, and start **SubConscious Engine**.

Read this entire file before changing anything. Do not assume services, paths, or credentials exist unless you have verified them on the machine you are working on.

---

## 1. What this program does

SubConscious Engine is a **long-running Python daemon**. It:

1. Watches configured **entry points** (directories, inbound HTTP API, outbound HTTP polls, idle poller).
2. Turns what it finds into **events**.
3. **Routes** each event using rules in the config file.
4. **Injects** a message into one or more Hermes sessions via the **SubConscious Adapter**.

It does **not** run inside the Hermes Gateway process. It is a separate program that talks to external HTTP services.

### 1.1 Hermes agent: handling nudges

If you are **Hermes** (the Agent receiving injected messages), you also need the **nudge-handling skill** in this repository — not just the engine daemon.

| Step | Action |
|------|--------|
| 1 | Pull this repo (`git pull`) |
| 2 | Run `./hermes/install-skill.sh` to link skills into `~/.hermes/skills/` (nudges, config, inbox-digest-curator) |
| 3 | Ensure the engine is running with `POST /ack` support (restart after sync) |
| 4 | On every subconscious injection: read `hermes/subconscious-engine-nudges/SKILL.md` and use `scripts/ack-engine.sh` |

The skill documents **every nudge type** (maintenance, research, pending decisions, weather, inbox, vault rules, alerts, tests) and the **two-step ack protocol** (`in_progress` → `done`). See **section 14** for the full install path.

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
| `entry_points[].url` | Required for `http_poll` — remote URL to fetch |
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
    type: directory          # directory | http | http_poll | idle
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
| `http` | **Inbound** — starts a local HTTP server (default `127.0.0.1:8770`). External systems POST events to the engine. |
| `http_poll` | **Outbound** — engine calls a remote URL on an interval. Response body is turned into events. |
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

**Outbound HTTP poll** — minimal example (disabled by default):

```yaml
  - id: external_poll
    type: http_poll
    enabled: false
    url: "http://127.0.0.1:9999/api/events"
    method: GET
    poll_interval_seconds: 120
    api_key: ""
    headers:
      Accept: application/json
    handle:
      response_format: events_list
      items_key: events
      id_field: id
      default_event_type: custom
      default_priority: 0
```

See **section 13** for the full outbound polling guide (response formats, routing, dedup, verification).

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

Persists cooldowns, idle counters, processed inbox files, vault rule last-run times, and **outbound poll dedup** (`poll_seen`). Do not delete while the engine is running.

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
- `REST event source api listening on 127.0.0.1:8770` (if inbound HTTP enabled)
- `HTTP poll source external_poll polling http://... every 120s` (if `http_poll` enabled)
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

### 7.2 Agent acknowledgements (`POST /ack`)

Nudge types (idle, weather, pending decisions, etc.) run **independently**. Each has its own `cooldown_key`. Hermes may be working on one nudge while another fires — unless Hermes tells the engine what's happening.

When Hermes handles a subconscious injection **without User typing**, the gateway still looks idle. The engine needs a **feedback channel**.

**Two ack statuses:**

| `status` | When Hermes calls it | Effect |
|----------|----------------------|--------|
| `in_progress` | Started working on the nudge (sub-agent spawned, etc.) | Counts as **activity**; blocks **same** `cooldown_key` from firing again; does **not** start cooldown yet |
| `done` (or `completed`) | Finished handling the nudge | Sets cooldown for that key; clears in-progress; counts as activity |

**1. When you start work** (counts as activity, suppresses duplicate nudges of the same type):

```bash
curl -s -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -d '{
    "cooldown_key": "idle_engine",
    "status": "in_progress",
    "event_id": "optional-event-id"
  }'
```

**2. When you finish work:**

```bash
curl -s -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -d '{
    "cooldown_key": "idle_engine",
    "status": "done",
    "cooldown_minutes": 60,
    "reset_idle_period": true
  }'
```

| Field | Required | Effect |
|-------|----------|--------|
| `cooldown_key` | yes | Which nudge type (must match the injected event) |
| `status` | no | `in_progress` or `done` / `completed` (default: `done`) |
| `cooldown_minutes` | no | Used on `done` only; default: `idle.cooldown_minutes` |
| `reset_idle_period` | no | On `done`: clears idle-period wake flag |
| `event_id` | no | Logged only |

**Per-key isolation:** `in_progress` on `idle_engine` blocks another idle nudge, but **does not** block `weather` or `pending_decisions` (different keys). Ack each type separately.

**Finding the cooldown_key:** injected messages end with:

```
[engine-ack:idle_engine|in_progress,done]
```

Parse the key before `|` and call `/ack` twice per nudge (start → `in_progress`, finish → `done`).

**Hermes:** use the bundled helper instead of raw curl when possible:

```bash
/path/to/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh \
  idle_engine in_progress

/path/to/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh \
  idle_engine done --minutes 60 --reset-idle
```

Full per-nudge procedures: `hermes/subconscious-engine-nudges/SKILL.md` (install via `./hermes/install-skill.sh`).

Use the same `api_key` auth as `POST /events` if configured.

### 7.3 Send a test event via HTTP

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

### 7.4 Send a test event via file drop

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

### 7.5 Read logs

```bash
tail -f ~/.hermes/logs/subconscious-engine.log
# or for test profile:
tail -f ~/.hermes/logs/subconscious-engine-test.log
```

Look for: `Event <id> type=custom delivered 1/1` (success) or warnings about no targets / cooldown.

### 7.6 Verify outbound HTTP polling (without starting a second engine)

If an engine instance is **already running** on this host, do **not** start another copy to test `http_poll`. Use one of these approaches instead.

**Option A — read logs on the running instance**

After enabling `http_poll` in the live config and restarting that instance (only if you are allowed to restart it):

```bash
tail -f ~/.hermes/logs/subconscious-engine.log
```

Look for:

- `HTTP poll source <id> polling <url> every <N>s` at startup
- `HTTP poll <id> published event <event_id> (key=<dedupe_key>)` after a successful fetch

**Option B — run unit tests in the repo (safe, no daemon)**

From the repository root, with venv active:

```bash
cd /home/hermes/workspace/subconscious-engine
pytest tests/test_rest_poll_parse.py tests/test_rest_poller.py -q
```

These tests use a temporary stub HTTP server on a **random free port** — not 8770/8771.

**Option C — manual curl of the remote feed**

Verify the URL you configured returns parseable JSON before enabling the entry point:

```bash
curl -s "http://YOUR-REMOTE-HOST/api/events"
```

The body must match one of the formats in section 13.3.

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
7. **Do not start a second engine instance** on the same host if one is already running (port 8770 and shared state would conflict). Run `pytest` for development instead of `python -m src`.
8. **Outbound `http_poll`** pulls from remote URLs — only enable when the feed is trusted. Test the URL with `curl` and `pytest tests/test_rest_poll_parse.py` before enabling in production config.

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
| Port already in use | Another process on 8770/8771 | Change inbound `http` entry point `port` or do not start a second engine |
| HTTP poll returns nothing | Bad JSON, empty `text`, or all items already seen | `curl` the URL; check `poll_seen` in `state.yaml`; see section 13.6 |
| HTTP poll 401/403 | Remote API requires auth | Set `api_key` or add headers under `entry_points[].headers` |

---

## 13. Outbound HTTP polling (`http_poll`) — full guide

This section explains how to configure the engine to **pull** events from an external HTTP API.

### 13.1 Inbound vs outbound HTTP

| | Inbound (`type: http`) | Outbound (`type: http_poll`) |
|--|------------------------|------------------------------|
| Direction | External → engine | Engine → external |
| Who listens | Engine binds a port (e.g. 8770) | Remote service listens |
| Trigger | Client POSTs to `/events` | Engine GETs (or POSTs) on a timer |
| Config key | `host`, `port` | `url`, `poll_interval_seconds` |

Use **inbound** when another service pushes events to the engine.  
Use **outbound** when the engine must periodically fetch a remote queue or feed.

### 13.2 Step-by-step: enable outbound polling

1. **Confirm the remote URL works** from the engine host:
   ```bash
   curl -s -w "\nHTTP %{http_code}\n" "http://REMOTE-HOST/path/to/events"
   ```
   You should get HTTP 2xx and a body the engine can parse (section 13.3).

2. **Add or edit** an `http_poll` block under `entry_points` in the config file.

3. **Set a unique `id`** (e.g. `cron_feed`, `external_poll`). This id is used in routing rules and in state dedup.

4. **Set `enabled: true`** only when you are ready for live polling.

5. **Add a routing rule** that matches events from this entry point (section 13.5).

6. **Restart the engine** (or deploy config to the running instance's config path and restart that single instance).  
   Do not run a second engine on the same host.

7. **Watch logs** for `HTTP poll source ... polling ...` and `HTTP poll ... published event ...`.

### 13.3 Response formats (`handle.response_format`)

The engine reads the HTTP response **body as text**, then parses it according to `response_format`.

#### `events_list` (default)

Use when the remote API returns **one or more events per poll**.

**Format A — JSON array at root:**

```json
[
  {
    "id": "job-101",
    "text": "Run backup check on vault",
    "event_type": "alert",
    "priority": 10,
    "cooldown_key": "backup_check"
  }
]
```

**Format B — array nested under a key:**

```json
{
  "events": [
    {"id": "job-101", "text": "Hello from remote API", "event_type": "custom"}
  ]
}
```

If the array key is not `events`, `items`, or `data`, set `handle.items_key` explicitly:

```yaml
handle:
  response_format: events_list
  items_key: pending_jobs
```

**Rules for each item in the list:**

| Rule | Detail |
|------|--------|
| Must be a JSON object | Arrays of strings are skipped |
| Must have `text` | Non-empty string; items without `text` are skipped |
| `id` recommended | Used for dedup (see `id_field`); without it, a hash of text+type is used |
| Optional fields | Same as inbound events: `event_type`, `priority`, `cooldown_key`, `preferred_target`, `targets`, `metadata` |

If `event_type` is omitted, `handle.default_event_type` is used.  
If `priority` is omitted, `handle.default_priority` is used.

#### `single_event`

Use when each poll returns **exactly one** JSON object:

```json
{
  "id": "status-42",
  "text": "Disk usage above 90%",
  "event_type": "alert"
}
```

Config:

```yaml
handle:
  response_format: single_event
  default_event_type: custom
```

#### `open_meteo`

Use when polling the **Open-Meteo** forecast API (https://open-meteo.com/). No API key required.

Two modes (auto-selected from the response + config):

| Mode | When | API params | Dedup key |
|------|------|------------|-----------|
| **Hourly window** | `handle.forecast_hours > 0` and response has `hourly` | `hourly=...&forecast_hours=N` | `open-meteo:<location>:<window_start>` |
| **Daily summary** | `forecast_hours: 0` and response has `daily` | `daily=...&forecast_days=1` | `open-meteo:<location>:<date>` |

Hourly mode builds a **next N hours** outlook with storm/rain alerts and a ride/outdoors line. Set `poll_interval_seconds` to match `forecast_hours` (e.g. both 6h).

```yaml
handle:
  response_format: open_meteo
  location_name: "Warsaw, PL"
  forecast_hours: 6
  default_event_type: weather
```

See **section 13.11** for the Warsaw 6-hour example.

#### `text`

Use when the API returns **plain text** (not JSON):

```
Server room temperature is 28°C
```

The entire body becomes one event:

- `text` = body (trimmed)
- `event_type` = `handle.default_event_type`
- Dedup key = hash of the text

Config:

```yaml
handle:
  response_format: text
  default_event_type: alert
```

### 13.4 Config reference for `http_poll`

```yaml
entry_points:
  - id: my_remote_feed          # required — unique name
    type: http_poll               # required
    enabled: true                 # false = do not poll
    url: "http://host/path"       # required — full URL including path
    method: GET                   # GET or POST (default GET)
    poll_interval_seconds: 120    # seconds between polls (default 5 if omitted)
    api_key: ""                   # if set, sends Authorization: Bearer <api_key>
    headers:                      # optional extra request headers
      Accept: application/json
      X-Custom: value
    handle:
      response_format: events_list
      items_key: ""               # JSON key for array; empty = auto-detect
      id_field: id                # field used for deduplication
      default_event_type: custom
      default_priority: 0
```

| Field | Required | Description |
|-------|----------|-------------|
| `id` | yes | Entry point name; appears in `event.entry_point` and routing |
| `type` | yes | Must be `http_poll` |
| `enabled` | no | Default `true` in parser; set `false` to disable |
| `url` | yes | Remote URL to fetch |
| `method` | no | HTTP method (default `GET`) |
| `poll_interval_seconds` | no | Wait time between polls (default `5`) |
| `api_key` | no | If non-empty, adds `Authorization: Bearer ...` |
| `headers` | no | Additional request headers |
| `handle.response_format` | no | `events_list`, `single_event`, `text`, or `open_meteo` |
| `handle.items_key` | no | Key for nested array when body is an object |
| `handle.id_field` | no | Dedup field name (default `id`) |
| `handle.location_name` | no | Label for `open_meteo` (e.g. `Warsaw, PL`) |
| `handle.forecast_hours` | no | Hourly window size; `0` = daily mode |
| `handle.default_event_type` | no | Fallback event type |
| `handle.default_priority` | no | Fallback priority |

### 13.5 Routing polled events

Polled events flow through the same router as file/HTTP/idle events. Match on `event_type` and optionally `entry_point`:

```yaml
routing:
  rules:
    - name: remote_alerts
      match:
        event_type: alert
        entry_point: my_remote_feed
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        cooldown_minutes: 30
        priority: 40

    - name: remote_default
      match:
        event_type: custom
        entry_point: my_remote_feed
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        priority: 5
```

If you omit `entry_point` in the match block, the rule applies to that `event_type` from **any** entry point.

### 13.6 Deduplication and state

Each parsed item gets a **dedupe key**:

1. Value of `id_field` (default `id`) if present and non-empty
2. Otherwise `hash:<sha256-prefix>` from `text` + `event_type`

Before publishing, the engine checks `state.yaml`:

```yaml
poll_seen:
  my_remote_feed:
    job-101: 1781458800.0
    job-102: 1781458860.0
```

- If the key already exists under `poll_seen.<entry_point_id>`, the item is **skipped** (not injected again).
- Keys are recorded only after the event bus accepts the event.

To force re-delivery of a remote item (e.g. for testing), remove its key from `poll_seen` in the state file **while the engine is stopped**, or use a new `id` on the remote side.

**Note:** Dedup is per entry point id. Two `http_poll` entry points pointing at the same URL keep separate `poll_seen` maps.

### 13.7 Authentication examples

**Bearer token via `api_key`:**

```yaml
api_key: "your-remote-token"
```

Engine sends: `Authorization: Bearer your-remote-token`

**Custom header:**

```yaml
api_key: ""
headers:
  X-API-Key: your-remote-token
  Accept: application/json
```

### 13.8 Error handling

| HTTP result | Engine behaviour |
|-------------|------------------|
| 2xx with parseable body | Events extracted; new items published |
| 2xx with empty/unparseable body | No events; logs nothing at INFO |
| 4xx / 5xx | Warning logged; waits for next poll interval |
| Connection error | Exception logged; waits for next poll interval |

The engine does **not** crash on poll failures. It retries on the next interval.

### 13.9 Complete worked example

Remote service at `http://192.168.1.50:8080/api/pending` returns:

```json
{
  "events": [
    {
      "id": "notify-001",
      "text": "[SUBCONSCIOUS] Backup job failed on nas-01",
      "event_type": "alert",
      "priority": 20,
      "cooldown_key": "backup_failed"
    }
  ]
}
```

Config snippet:

```yaml
entry_points:
  - id: backup_feed
    type: http_poll
    enabled: true
    url: "http://192.168.1.50:8080/api/pending"
    method: GET
    poll_interval_seconds: 60
    headers:
      Accept: application/json
    handle:
      response_format: events_list
      items_key: events
      id_field: id
      default_event_type: custom

routing:
  rules:
    - name: backup_alerts
      match:
        event_type: alert
        entry_point: backup_feed
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        cooldown_minutes: 60
        priority: 50
```

After restart, within 60 seconds the engine should log publication of `notify-001`. A second poll with the same `id` will not inject again.

### 13.11 Example: 6-hour weather outlook for Warsaw (Open-Meteo)

Poll every **6 hours**, fetch the **next 6 hours** of hourly forecast, inject an advisory the Agent can use to warn about storms or say if a bike ride is OK.

**Repository file:** `config/examples/weather-warsaw.yaml`

**How the timing fits together:**

```
poll_interval_seconds: 21600  ──►  engine calls API every 6 hours
forecast_hours=6 (URL)        ──►  API returns next 6 hourly slots
handle.forecast_hours: 6      ──►  parser formats those 6 hours
dedup: window start time      ──►  one inject per poll (e.g. 08:00, 14:00, 20:00)
```

**1. Verify the API:**

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=52.2297&longitude=21.0122&hourly=temperature_2m,precipitation_probability,weather_code,precipitation,wind_speed_10m&forecast_hours=6&timezone=Europe%2FWarsaw"
```

Response must include an `hourly` object with 6 `time` entries.

**2. Entry point config:**

```yaml
entry_points:
  - id: weather_warsaw
    type: http_poll
    enabled: false
    url: "https://api.open-meteo.com/v1/forecast?latitude=52.2297&longitude=21.0122&hourly=temperature_2m,precipitation_probability,weather_code,precipitation,wind_speed_10m&forecast_hours=6&timezone=Europe%2FWarsaw"
    method: GET
    poll_interval_seconds: 21600
    headers:
      Accept: application/json
      User-Agent: subconscious-engine/1.0
    handle:
      response_format: open_meteo
      location_name: "Warsaw, PL"
      forecast_hours: 6
      default_event_type: weather
      default_priority: 1
```

| Parameter | Must match | Purpose |
|-----------|------------|---------|
| `poll_interval_seconds` | `21600` (6h) | How often to fetch |
| `forecast_hours` in URL | `6` | API returns 6 hourly steps |
| `handle.forecast_hours` | `6` | Parser formats 6 hours |
| `timezone` | `Europe/Warsaw` | Local hour labels |

**3. Routing** (cooldown 360 min = 6h, aligned with poll):

```yaml
routing:
  rules:
    - name: warsaw_weather
      match:
        event_type: weather
        entry_point: weather_warsaw
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        cooldown_minutes: 360
        priority: 5
```

**4. Example injected message:**

```
[SUBCONSCIOUS] Weather next 6h for Warsaw, PL
Window: 2026-06-15T16:00 → 2026-06-15T21:00

Alerts:
  ⚠️ Thunderstorm expected around 18:00
  ⚠️ Heavy rain expected around 19:00

Hourly:
  16:00: 16.6°C, Slight rain, rain 66%, 0.2 mm, wind 12.0 km/h
  ...

Ride/outdoors: Not recommended — thunderstorm risk in this window.

Agent: warn User only if alerts above are significant; otherwise a brief OK is fine.
```

Storm/rain alerts raise event `priority` to at least 15 for routing.

**5. Dedup:** Key `open-meteo:Warsaw, PL:2026-06-15T16:00` — each 6-hour window injects once.

**6. Test without the daemon:** `pytest tests/test_open_meteo.py -q`

**7. Other cities:** Change coordinates, `timezone`, and `location_name`. Keep URL `forecast_hours` and `handle.forecast_hours` in sync.

### 13.12 Troubleshooting outbound polling

| Symptom | Check |
|---------|--------|
| No log line at startup | `enabled: false` or wrong `type` |
| `HTTP poll ... returned 404` | `curl` the `url` from the engine host |
| Poll runs but no inject | Items missing `text`; or already in `poll_seen`; or no matching routing rule |
| Wrong event type | Remote omitted `event_type` — engine uses `default_event_type` |
| Duplicate injects | Remote changes `id` on every poll — stabilise ids server-side |
| Auth failures | Set `api_key` or `headers`; verify with `curl -H ...` |

---

## 14. Hermes nudge-handling skill (full install)

This repository ships a **Hermes skill** so the Agent knows how to handle every subconscious nudge and call `POST /ack` correctly.

### 14.1 What is included

```
hermes/
├── install-skill.sh                          # Symlink skill into ~/.hermes/skills/
└── subconscious-engine-nudges/
    ├── SKILL.md                              # Complete nudge + ack procedures
    └── scripts/
        └── ack-engine.sh                     # POST /ack helper
```

### 14.2 Install (after git pull)

```bash
cd /path/to/subconscious-engine
git pull
chmod +x hermes/install-skill.sh hermes/subconscious-engine-nudges/scripts/ack-engine.sh
./hermes/install-skill.sh
```

This creates:

`~/.hermes/skills/devops/subconscious-engine-nudges` → `hermes/subconscious-engine-nudges/` in the repo.

Hermes loads skills from `~/.hermes/skills/` automatically.

### 14.3 Optional environment

Add to `~/.hermes/.env` if you do not want the helper to read engine config:

```bash
SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770
SUBCONSCIOUS_ENGINE_API_KEY=    # only if entry_points[].api_key is set
```

Otherwise `ack-engine.sh` reads `host`, `port`, and `api_key` from the first enabled `http` entry point in `~/.hermes/subconscious-engine/config.yaml`.

### 14.4 What Hermes must do on every nudge

1. Recognize injections (`[SUBCONSCIOUS` prefix, optional `[engine-ack:KEY|...]` footer).
2. **`ack-engine.sh KEY in_progress`** — immediately when starting work.
3. Handle per nudge type (see SKILL.md section 5).
4. **`ack-engine.sh KEY done`** — when finished, with appropriate `--minutes`.
5. Summarize for User.

### 14.5 Nudge types covered in SKILL.md

| Type | `cooldown_key` (typical) | Summary |
|------|--------------------------|---------|
| Maintenance | `idle_engine` | One due task from tasks.md |
| Research | `idle_engine` | One research topic → Reports |
| Pending decisions | `pending_decisions` | Wake nudge — classify decision items |
| Weather (Open-Meteo) | `open-meteo:...` | Advisory; notify if urgent |
| Inbox notify | `inbox:<file>` | Summarize for User |
| Inbox delegate/review | `inbox:<file>` | File, delegate, or routine |
| Vault rule | `vault_rule:<id>` | Follow matched rule prompt |
| Alert / custom / broadcast | footer or `event_type` | Follow injected instructions |
| Test | — | Acknowledge only; no ack/work |

### 14.6 Verify ack path works

```bash
curl -s http://127.0.0.1:8770/health

./hermes/subconscious-engine-nudges/scripts/ack-engine.sh agent_skill_test in_progress
./hermes/subconscious-engine-nudges/scripts/ack-engine.sh agent_skill_test done --minutes 1
```

Use a throwaway `cooldown_key` for verification (e.g. `agent_skill_test`).

### 14.7 Engine restart after pull

The running copy of the engine will not have `/ack` until that copy is updated and restarted:

```bash
# On the host where the engine runs — do NOT start a second instance
sudo systemctl restart subconscious-engine.service
# or restart the single background process Hermes uses
```

### 14.8 Queue delivery (do not interrupt mid-task)

SubConscious Engine injects with `"delivery": "queue"` by default. When Hermes is already working, nudges wait for the **next turn** instead of interrupting (same FIFO as `/queue`).

**Requires** an updated [SubConscious-Adapter](https://github.com/KarlitaHermes/SubConscious-Adapter) plugin that honors the `delivery` field. After pulling both repos:

```bash
# Adapter plugin (symlink or copy to plugins dir, then restart gateway)
cd /path/to/subconscious-adapter
git pull
# e.g. ln -sfn $(pwd) ~/.hermes/plugins/subconscious-adapter
sudo systemctl restart hermes-gateway

# Engine
cd /path/to/subconscious-engine
git pull
sudo systemctl restart subconscious-engine.service
```

No Hermes gateway core changes are required — the adapter uses the gateway's existing `_enqueue_fifo` when the session is busy.

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
| `VERSION-NOTES.md` | **Upgrade notes** — queue delivery, install steps, rollback |
| `hermes/subconscious-engine-nudges/SKILL.md` | **Hermes skill** — handle all nudge types + `/ack` |
| `hermes/subconscious-engine-nudges/scripts/ack-engine.sh` | Shell helper for `POST /ack` |
| `hermes/install-skill.sh` | Install nudges + config + inbox-digest-curator skills |
| `config.yaml.example` | Full production config template (includes `http_poll` + Warsaw weather) |
| `examples/WORKING-DEPLOYMENT.md` | **Live deployment** — sanitized configs, file map, Hermes gateway snippet |
| `docs/CRON-AND-INBOX.md` | **Cron → inbox → SE** — `deliver: local`, filename prefixes, agent workflow |
| `config/examples/weather-warsaw.yaml` | Copy-paste Open-Meteo Warsaw `http_poll` example |
| `config.test.yaml` | Safe test profile (idle off) |
| `ARCHITECTURE.md` | Internal design overview |
| `CONFIG.md` | Shorter config reference (partially legacy) |
| `TODO.md` | Known limitations (CLI inject, testing rules) |
| `tests/test_rest_poll_parse.py` | Unit tests for poll response parsing |
| `tests/test_rest_poller.py` | Integration tests with ephemeral stub server |
| `tests/test_open_meteo.py` | Open-Meteo Warsaw forecast parser tests |

When instructions conflict, prefer this file for setup/start steps and `config.yaml.example` for the canonical config shape.
