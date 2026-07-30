# SubConscious Engine — Configuration Reference

Authoritative full example: `config.yaml.example`.  
Production-shaped (sanitized): `examples/working-deployment/engine-config.production.yaml`.

Default path: `~/.hermes/subconscious-engine/config.yaml`  
Override: `--config PATH` or `SUBCONSCIOUS_CONFIG`.

## Top-level keys

```yaml
gateway:
  url: "http://127.0.0.1:8642"
  api_key: ""  # empty → load API_SERVER_KEY from ~/.hermes/.env

adapter:
  url: "http://127.0.0.1:8769"

idle:
  threshold_minutes: 30      # inactivity before idle nudges
  cooldown_minutes: 60       # default cooldown if rule omits one
  target_source: "telegram"  # idle always uses this source
  fallback_sources: []       # router only; do not rely on cli (see TODO.md)
  vault_root: "~/path/to/your/obsidian-vault"
  wake_grace_minutes: 10
  nudge_budget_per_hour: 6   # 0 = unlimited successful nudges / hour

poll_interval_seconds: 60    # idle source poll interval

entry_points: []             # see below
routing:
  rules: []                  # see below

logging:
  level: "INFO"
  file: "~/.hermes/logs/subconscious-engine.log"
  max_bytes: 10485760
  backup_count: 3

state:
  file: "~/.hermes/subconscious-engine/state.yaml"
```

Legacy `sources` and `router` blocks are still accepted and migrated automatically.

## Entry points

Each item needs `id`, `type`, and usually `enabled`.

### `directory`

| Field | Notes |
|-------|--------|
| `path` | Directory to poll |
| `poll_interval_seconds` | Default 5 |
| `archive_dir` | Optional move-after-process (event_file) |
| `handle.handler` | `event_file` \| `inbox` \| `vault_rules` |
| `handle.parser` | `auto` \| `json` \| `yaml` \| `text` (event_file) |
| `handle.default_event_type` / `default_priority` | Defaults for emitted events |

### `http` (inbound)

| Field | Notes |
|-------|--------|
| `host` / `port` | Default `127.0.0.1:8770` |
| `api_key` | Optional Bearer for `POST /events` and `POST /ack` |

Endpoints: `GET /health`, `POST /events`, `POST /ack`.

### `http_poll` (outbound)

| Field | Notes |
|-------|--------|
| `url` / `method` / `headers` | Fetch target |
| `poll_interval_seconds` | How often to fetch |
| `api_key` | Optional Bearer on the outbound request |
| `handle.response_format` | `events_list` \| `single_event` \| `text` \| `open_meteo` |
| `handle.items_key` / `id_field` | List parse + dedupe |
| `handle.location_name` / `forecast_hours` | Open-Meteo prompts |

### `idle`

No extra fields required. Uses top-level `idle:` and `poll_interval_seconds`.

Emits `maintenance` / `research` (alternating) and `pending_decisions` when vault decisions warrant a wake nudge. Shared cooldown key for idle work: `idle_engine`.

## Routing rules

Nested form (preferred):

```yaml
routing:
  rules:
    - name: maintenance
      match:
        event_type: maintenance   # or "*"
        entry_point: idle         # optional filter
        min_event_priority: 0
      deliver:
        target_sources: ["telegram"]
        max_targets: 1
        broadcast: false
        cooldown_minutes: 60
        priority: 10              # rule selection priority
        active_hours: []          # hard gate — drop outside (no defer)
        active_days: []           # weekday 0=Mon; empty = always
        preferred_window:         # soft: wait if soon, else ASAP
          hours: [0, 1, 2]        # prefer 00:00–02:59 local
          max_wait_hours: 12      # if next window farther → deliver now
          fallback: asap
```

`preferred_window` parks until the next matching hours when that start is within `max_wait_hours`; otherwise delivers immediately. If still undelivered when the window ends, a 60s flush promotes with ASAP. Distinct from `active_hours` (hard drop).

Flat `event_type` / `target_sources` form still works. Highest matching rule priority wins; exact `event_type` beats `*` at the same priority.

If no rule matches (including outside active hours/days), the event is suppressed.

## Environment variables

| Variable | Description |
|----------|-------------|
| `SUBCONSCIOUS_CONFIG` | Path to config YAML |
| `API_SERVER_KEY` | Via `~/.hermes/.env` when `gateway.api_key` is empty |
| `GATEWAY_URL` | Override `gateway.url` |
| `SUBCONSCIOUS_URL` | Override `adapter.url` |

## State file

Engine-owned YAML (do not commit live state). Shape reference: `examples/working-deployment/state.example.yaml`.

Notable keys:

| Key | Role |
|-----|------|
| `cooldowns` | Per-key last success / done timestamps |
| `tasks_in_progress` | Agent `in_progress` acks (expire if abandoned) |
| `acks` / `deliveries` | Recent history (capped) |
| `deferred` | Preferred-window park queue (per cooldown_key) |
| `poll_seen` / `processed_files` | Deduplication |
| `idle_period_active` / `idle_trigger_count` | Idle source bookkeeping |
| `nudge_timestamps` | Budget window |
| `active_sessions` | Per-source live session; change clears in_progress |

## systemd

```bash
sudo cp systemd/subconscious-engine.service /etc/systemd/system/
# or use examples/working-deployment/systemd-service.example (edit paths/user)
sudo systemctl daemon-reload
sudo systemctl enable --now subconscious-engine
journalctl -u subconscious-engine -f
```

## Testing without live injects

Use `config.test.yaml` (`python -m src --config config.test.yaml`): idle off, separate port/state/logs. Prefer mocked HTTP in pytest. See `TODO.md` testing guidelines.
