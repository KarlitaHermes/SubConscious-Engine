# Working deployment examples

These files are **sanitized snapshots** of a real Hermes + SubConscious setup. They show what is actually wired together in production—not the generic templates in `config.yaml.example`.

**Source:** Sanitized from a live Hermes deployment file map (2026-06). Values are censored: no API keys, no real session IDs, vault path replaced with a placeholder, weather uses generic `Example City`.

## Why this exists

| Problem | How these examples help |
|---------|-------------------------|
| `config.yaml.example` is exhaustive but not what we run | `working-deployment/engine-config.production.yaml` matches the **live** engine config shape |
| Adapter + gateway + skill are separate trees | `FILE-MAP.md` lists every path and which repo owns it |
| `state.yaml` must never be committed | `state.example.yaml` shows **structure** only |
| Hermes `config.yaml` is huge and secret-heavy | `hermes-gateway.snippet.yaml` is the **SubConscious-only** excerpt |

## What is in `examples/working-deployment/`

| File | Live path it mirrors | Safe to copy as-is? |
|------|----------------------|---------------------|
| `engine-config.production.yaml` | `~/.hermes/subconscious-engine/config.yaml` | **Edit** `vault_root` and cooldowns for your machine |
| `engine-config.minimal.yaml` | `~/.hermes/subconscious-engine/config-minimal.yaml` | Idle + file drop only (no weather); good minimal start |
| `state.example.yaml` | `~/.hermes/subconscious-engine/state.yaml` | **Do not copy** — engine creates this; read for field meanings |
| `hermes-gateway.snippet.yaml` | `~/.hermes/config.yaml` (platforms + plugins) | Merge into your Hermes config |
| `systemd-service.example` | `/etc/systemd/system/subconscious-engine.service` | Replace `WorkingDirectory` / `User` |
| `events/sample-custom-nudge.json` | `~/.hermes/subconscious-engine/events/*.json` | Drop-in test event |
| `inbox/news-digest-*-example.md` | `vault/COMMS/Inbox/*.md` | Cron output shape (sanitized) |
| `FILE-MAP.md` | Full integration file map | Reference |

## Repos and install locations

```
SubConscious-Engine (this repo)
  └── src/                          # daemon source — systemd runs python -m src
  └── docs/CRON-AND-INBOX.md        # cron → inbox → SE pipeline howto
  └── hermes/                       # Hermes skills (install via install-skill.sh)
      ├── subconscious-engine-nudges/
      ├── subconscious-engine-config/
      └── inbox-digest-curator/
  └── examples/working-deployment/  # ← sanitized configs + samples

SubConscious-Adapter (sibling repo)
  └── __init__.py, plugin.yaml      # gateway plugin
  └── ~/.hermes/plugins/subconscious-adapter → symlink to checkout

Hermes (not in these repos)
  └── ~/.hermes/config.yaml         # platforms.subconscious + plugins.enabled
  └── ~/.hermes/skills/subconscious-engine-nudges/   # production skill (User-managed)
  └── ~/.hermes/subconscious-engine/    # runtime config + state (DO NOT COMMIT)
  └── ~/.hermes/logs/subconscious-engine.log
```

## Quick install from examples

**1. Engine config**

```bash
mkdir -p ~/.hermes/subconscious-engine/events/processed
cp examples/working-deployment/engine-config.production.yaml \
   ~/.hermes/subconscious-engine/config.yaml
# Edit vault_root and any paths
```

**2. Adapter plugin** (see [SubConscious-Adapter examples/README.md](https://github.com/KarlitaHermes/SubConscious-Adapter/blob/main/examples/README.md))

```bash
ln -sfn ~/workspace/subconscious-adapter ~/.hermes/plugins/subconscious-adapter
```

**3. Hermes gateway** — merge `hermes-gateway.snippet.yaml` into `~/.hermes/config.yaml`, then:

```bash
sudo systemctl restart hermes-gateway
```

**4. Engine service**

```bash
sudo cp examples/working-deployment/systemd-service.example \
   /etc/systemd/system/subconscious-engine.service
# Edit paths in the unit file, then:
sudo systemctl daemon-reload
sudo systemctl enable --now subconscious-engine
```

**5. Skills** — install all three from this repo:

```bash
chmod +x hermes/install-skill.sh
./hermes/install-skill.sh
```

| Skill | Purpose |
|-------|---------|
| `subconscious-engine-nudges` | ACK protocol, every nudge type |
| `subconscious-engine-config` | Edit config, restart engine |
| `inbox-digest-curator` | Cron inbox drops (news, email, research) |

Hermes must run `ack-engine.sh` for notify gate / cooldown coordination. **Cron jobs:** see `docs/CRON-AND-INBOX.md` — use `deliver: local`, write `*.md` to `COMMS/Inbox/`, never deliver digests directly to Telegram.

## Production profile highlights

Compared to `config.yaml.example`, the live production config:

- **Idle:** 60 min threshold, 240 min cooldown, telegram-only (no CLI fallback)
- **Entry points:** idle, file drop (`events_drop`), **inbox** (`COMMS/Inbox/` for crons), inbound HTTP (`api` :8770), Open-Meteo poll (`weather_example`, every 6 h)
- **Routing:** per-entry-point rules with longer cooldowns (e.g. weather 720 min, idle maintenance 480 min)
- **Notify gate:** Hermes acks via `POST /ack` on 8770; engine suppresses duplicate nudges

## Do not publish / commit

- `~/.hermes/subconscious-engine/state.yaml` — runtime cooldowns, session IDs, ack history
- `~/.hermes/subconscious-engine/config.yaml.bak`
- `~/.hermes/logs/*`
- Full `~/.hermes/config.yaml` — contains gateway API keys and platform secrets

## Related docs

- `docs/CRON-AND-INBOX.md` — cron `deliver: local` → inbox → SE → agent
- `UPGRADE-HERMES-version.md` — upgrade both repos
- `config.yaml.example` — full option reference
- `config/examples/weather-warsaw.yaml` — optional real-city Open-Meteo fragment (working examples use generic `weather_example` instead)
- `README-AGENT.md` — agent-oriented setup
