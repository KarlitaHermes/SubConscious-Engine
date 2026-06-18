# Nudge handling — quick reference

Full skill: `hermes/subconscious-engine-nudges/SKILL.md`

## Ack protocol

1. **Before work:** `ack-engine.sh COOLDOWN_KEY in_progress`
2. **After work:** `ack-engine.sh COOLDOWN_KEY done --minutes 60 --reset-idle`

Footer on injected messages: `[engine-ack:KEY|in_progress,done]`

## Cooldown keys by type

| Type | Typical key |
|------|-------------|
| Maintenance / research | `idle_engine` |
| Pending decisions | `pending_decisions` |
| Weather | `open-meteo:<location>:<window>` |
| Inbox file | `inbox:<filename>` |
| Vault rule | `vault_rule:<rule_id>` |
| Custom / test | set in payload or use `event_type` |

## Test messages

`[SUBCONSCIOUS ENGINE TEST]` — acknowledge in chat; use throwaway `cooldown_key`; do not block production keys.

## Health

```bash
curl -s http://127.0.0.1:8770/health
```

## Queue delivery

Engine sends `delivery: queue` — nudges do not interrupt a busy session. Requires current SubConscious-Adapter plugin.

## Notify gate

Engine suppresses duplicate nudges when: cooldown active, same key `in_progress`, no routing rule, poll item already seen. **Always ack `in_progress` promptly.**
