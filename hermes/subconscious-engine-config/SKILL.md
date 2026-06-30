---
name: subconscious-engine-config
category: devops
description: Manage SubConscious Engine configuration — entry points, routing, idle tuning, and restarts
---

# SubConscious Engine — configuration

Procedures for `~/.hermes/subconscious-engine/config.yaml`: entry points, routing rules, idle thresholds, and service restarts.

**Canonical examples (sanitized):** `examples/working-deployment/` in the subconscious-engine repo  
**Cron → inbox pipeline:** `docs/CRON-AND-INBOX.md`  
**Nudge ACK protocol:** `hermes/subconscious-engine-nudges/SKILL.md`

---

## Config location

| File | Purpose |
|------|---------|
| `~/.hermes/subconscious-engine/config.yaml` | **Active** engine config |
| `~/.hermes/subconscious-engine/config-minimal.yaml` | Optional minimal profile (idle + file drop only) |
| `examples/working-deployment/engine-config.production.yaml` | Production-shaped template in repo |

`ack-engine.sh` reads `SUBCONSCIOUS_ENGINE_URL` from env, else parses the first enabled `http` entry point in `config.yaml`.

---

## Key sections (current schema)

### `gateway` — idle activity signal

```yaml
gateway:
  url: http://127.0.0.1:8642
  api_key: ""   # or from ~/.hermes/.env
```

### `adapter` — inject target

```yaml
adapter:
  url: http://127.0.0.1:8769
```

### `idle` — idle detector entry point

```yaml
idle:
  threshold_minutes: 60
  cooldown_minutes: 240
  target_source: telegram
  fallback_sources: []
  vault_root: ~/path/to/your/obsidian-vault
  wake_grace_minutes: 10
```

### `entry_points` — event sources

| `type` | `id` example | Purpose |
|--------|--------------|---------|
| `idle` | `idle` | Maintenance / research / pending_decisions |
| `directory` + `handler: event_file` | `events_drop` | JSON/YAML/txt drop dir |
| `directory` + `handler: inbox` | `inbox` | **Cron output** — `COMMS/Inbox/*.md` |
| `http` | `api` | Inbound `POST /events`, `POST /ack` (default :8770) |
| `http_poll` | `weather_example` | Open-Meteo, external feeds |

See `docs/CRON-AND-INBOX.md` for inbox + cron setup.

### `routing.rules` — match + deliver

Nested form:

```yaml
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

Cooldowns are per rule (`deliver.cooldown_minutes`) and per ack key (`cooldown_key` on events).

### `state` — persistence

```yaml
state:
  file: ~/.hermes/subconscious-engine/state.yaml
```

Do **not** edit `state.yaml` by hand — cooldowns, `tasks_in_progress`, and `poll_seen` are engine-managed. Shape: `examples/working-deployment/state.example.yaml`.

---

## Common changes

### Enable inbox for cron output

1. Add `inbox` entry point (path = vault `COMMS/Inbox/`)
2. Add `inbox_notify` routing rule
3. Restart engine
4. Ensure crons use `deliver: local` and write `news-digest-*.md` etc.

### Tune idle spam

- Increase `idle.cooldown_minutes` and per-rule `cooldown_minutes` (maintenance/research)
- Hermes must ack `idle_engine` / `pending_decisions` — see nudges skill
- Notify gate blocks re-fire while `in_progress`

### Enable weather poll

Copy `weather_example` from `examples/working-deployment/engine-config.production.yaml` or `config/examples/weather-warsaw.yaml` (rename to your city).

---

## Restart (systemd)

```bash
sudo systemctl restart subconscious-engine
curl -s http://127.0.0.1:8770/health
journalctl -u subconscious-engine -n 30 --no-pager
```

**Single instance:** only one process on port 8770. `ss -tlnp | grep 8770`

---

## Backup before edits

```bash
cp ~/.hermes/subconscious-engine/config.yaml \
   ~/.hermes/subconscious-engine/config.yaml.$(date +%Y%m%d-%H%M%S).bak
```

---

## References (in repo)

| Doc | Topic |
|-----|--------|
| `references/nudge-handling.md` | ACK keys by nudge type |
| `docs/CRON-AND-INBOX.md` | Cron → inbox → SE |
| `examples/WORKING-DEPLOYMENT.md` | Full deployment map |
| `UPGRADE-HERMES-version.md` | Upgrade both repos |
