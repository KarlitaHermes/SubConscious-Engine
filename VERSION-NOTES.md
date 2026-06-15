# Version notes — queue delivery for subconscious injects

**Date:** 2026-06-15  
**Engine commit:** `62e0c9c` (requires adapter `759219e` or later)

## Summary

Subconscious nudges no longer interrupt Hermes when Rev (or the agent) is already mid-task. Injections use **queue delivery**: wait for the next turn if busy, run immediately if idle.

## What changed

### SubConscious-Engine (this repo)

| File | Change |
|------|--------|
| `src/delivery/subconscious.py` | `POST /inject` payload now includes `"delivery": "queue"` by default |
| `tests/test_delivery.py` | Tests for delivery field on inject client |
| `README-AGENT.md` | §14.8 install notes |
| `hermes/subconscious-engine-nudges/SKILL.md` | Notes queue behavior for Hermes |

### SubConscious-Adapter ([separate repo](https://github.com/KarlitaHermes/SubConscious-Adapter))

| File | Change |
|------|--------|
| `__init__.py` | `POST /inject` accepts `delivery` (`queue` \| `interrupt`); when `queue` and session busy, uses gateway FIFO enqueue |
| `README.md` | API docs for `delivery` field |

### Hermes gateway (hermes-agent)

**No changes.** Queue behavior uses the gateway's existing `_enqueue_fifo` via the adapter plugin.

## Why

Previously, subconscious injects went through `_handle_message` like a normal Rev message. With `busy_input_mode: interrupt` (default), a nudge fired while Hermes was working would **cut off** the current turn — bad for maintenance/weather/idle nudges during active work.

`/queue` already solves this for human chat. This release makes subconscious injects behave the same way automatically.

## Behavior

| Hermes session state | `delivery: "queue"` (default) | `delivery: "interrupt"` |
|----------------------|-------------------------------|-------------------------|
| Busy (agent running) | Enqueued — runs after current turn | Interrupts immediately |
| Idle | Runs immediately | Runs immediately |

SubConscious Engine always sends `queue`. Use `interrupt` only for manual/testing injects.

## Install / upgrade

Both repos must be updated. Order does not matter, but **restart both** after pulling.

### 1. SubConscious-Adapter

```bash
cd /path/to/subconscious-adapter
git pull origin main
# Ensure the plugin points at this checkout:
ln -sfn "$(pwd)" ~/.hermes/plugins/subconscious-adapter
sudo systemctl restart hermes-gateway
```

Verify adapter is listening:

```bash
curl -s http://127.0.0.1:8769/sessions | head
```

### 2. SubConscious-Engine

```bash
cd /path/to/subconscious-engine
git pull origin main
sudo systemctl restart subconscious-engine.service
```

Verify engine health (port from your config, default 8770):

```bash
curl -s http://127.0.0.1:8770/health
```

### 3. Hermes skill (optional but recommended)

```bash
cd /path/to/subconscious-engine
./hermes/install-skill.sh
```

### 4. Smoke test

```bash
# While Hermes is idle — should inject and respond normally
# While Hermes is busy — nudge should queue (no interrupt); runs after current turn ends
```

Manual inject with explicit delivery:

```bash
curl -s -X POST http://127.0.0.1:8769/inject \
  -H "Content-Type: application/json" \
  -d '{"session_id":"YOUR_SESSION_ID","text":"[SUBCONSCIOUS ENGINE TEST] queue delivery","delivery":"queue"}'
```

## Related (prior release on same branch)

Commit `9e28e74` added `POST /ack` (`in_progress` / `done`), outbound `http_poll`, and the Hermes nudge-handling skill. Queue delivery is independent but should be deployed together with a current adapter build.

## Rollback

- **Engine:** revert to `6ae45cf` — injects omit `delivery` (adapter treats as `queue` anyway on new adapter; old adapter ignores unknown field)
- **Adapter:** revert to `139af67` — ignores `delivery`, injects always interrupt when busy
- Restart gateway + engine after rollback
