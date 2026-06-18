# SubConscious — integration file map

Sanitized from a Hermes-generated dump. **Paths are as deployed on the reference host**; substitute your home directory and workspace paths.

## Safe in git (source repos)

| Area | Path | Files | Repo |
|------|------|-------|------|
| Engine source | `~/workspace/subconscious-engine/src/` | Python package | SubConscious-Engine |
| Engine tests | `~/workspace/subconscious-engine/tests/` | pytest | SubConscious-Engine |
| Engine docs | `~/workspace/subconscious-engine/*.md` | README, VERSION-NOTES, UPGRADE | SubConscious-Engine |
| **Working examples** | `~/workspace/subconscious-engine/examples/working-deployment/` | This directory | SubConscious-Engine |
| Adapter source | `~/workspace/subconscious-adapter/` | `__init__.py`, `plugin.yaml` | SubConscious-Adapter |
| Skill (repo copy) | `~/workspace/subconscious-engine/hermes/` | nudges, config, inbox-digest-curator |
| Cron + inbox howto | `~/workspace/subconscious-engine/docs/CRON-AND-INBOX.md` | Hermes cron → SE pipeline |
| systemd unit (template) | `~/workspace/subconscious-engine/systemd/` | `subconscious-engine.service` | SubConscious-Engine |

## Runtime only (never commit)

| Area | Path | Purpose |
|------|------|---------|
| Engine config | `~/.hermes/subconscious-engine/config.yaml` | Live entry points, routing, idle |
| Engine config backup | `~/.hermes/subconscious-engine/config.yaml.bak` | Manual backup |
| Orchestrator replica | `~/.hermes/subconscious-engine/config-orchestrator-replica.yaml` | Alternate profile on disk |
| Engine state | `~/.hermes/subconscious-engine/state.yaml` | Cooldowns, acks, poll_seen, deliveries |
| Test state | `~/.hermes/subconscious-engine/state.test.yaml` | pytest / manual test profile |
| Event drop dir | `~/.hermes/subconscious-engine/events/` | File watcher input |
| Processed events | `~/.hermes/subconscious-engine/events/processed/` | Archived after publish |
| Test events | `~/.hermes/subconscious-engine/events-test/` | `config.test.yaml` profile |
| Logs | `~/.hermes/logs/subconscious-engine.log` | Rotating file log |

## Hermes integration (sanitize before sharing)

| Area | Path | Purpose |
|------|------|---------|
| Adapter plugin (live) | `~/.hermes/plugins/subconscious-adapter/` | Symlink → adapter checkout |
| Hermes skill (live) | `~/.hermes/skills/devops/subconscious-engine-*` | Installed via `hermes/install-skill.sh` |
| Inbox (cron output) | `~/path/to/your/obsidian-vault/COMMS/Inbox/` | `*.md` from cron (`deliver: local`) |
| Hermes main config | `~/.hermes/config.yaml` | **Only** `platforms.subconscious` + `plugins.enabled` are needed for SubConscious — see `hermes-gateway.snippet.yaml` |

## Ports

| Service | Default | Role |
|---------|---------|------|
| Hermes gateway | 8642 | Session activity for idle detection |
| SubConscious Adapter | 8769 | `GET /sessions`, `POST /inject` |
| SubConscious Engine REST | 8770 | `GET /health`, `POST /events`, `POST /ack` |

## Data flow

```
entry points (idle, file, http_poll, …)
        ↓
   NotifyGate (cooldown / in_progress / rules)
        ↓
     Event bus → Router
        ↓
  SubConscious Adapter :8769  (delivery: queue)
        ↓
   Hermes gateway → telegram (etc.)
        ↓
   Hermes agent → POST :8770/ack (in_progress, done)
```
