# SubConscious upgrade & test — instructions for Hermes

**Goal:** Deploy the latest **SubConscious-Adapter** and **SubConscious-Engine** together. Two features ship as one upgrade:

1. **Queue delivery** — subconscious injects no longer interrupt a busy session (`delivery: "queue"`).
2. **Notify gate** — engine does not publish/inject when a nudge is in cooldown, in progress (`POST /ack`), or has no matching routing rule.

**Target commits (GitHub `main`):**

| Repo | Commit | Notes |
|------|--------|--------|
| [SubConscious-Adapter](https://github.com/KarlitaHermes/SubConscious-Adapter) | `772edef` or later (`759219e` = queue delivery) | Gateway plugin only |
| [SubConscious-Engine](https://github.com/KarlitaHermes/SubConscious-Engine) | `96a4670` or later | Includes notify gate |

**Do not modify** `hermes-agent` / gateway source. **Do not** run a second engine on port **8770** while `subconscious-engine.service` is already using it.

**Upgrade order:** adapter (gateway) first → engine systemd service second → integration tests last.

---

## 1. SubConscious-Adapter

```bash
cd /path/to/subconscious-adapter   # or clone: git clone https://github.com/KarlitaHermes/SubConscious-Adapter.git
git fetch origin
git checkout main
git pull origin main
git log -1 --oneline   # expect 772edef or newer

# Plugin must point at this checkout
ln -sfn "$(pwd)" ~/.hermes/plugins/subconscious-adapter

sudo systemctl restart hermes-gateway
```

**Verify adapter:**

```bash
curl -s http://127.0.0.1:8769/sessions | head
```

Pick a live `session_id` from that output for inject tests below.

**Manual queue inject test** (replace `SESSION_ID`):

```bash
curl -s -X POST http://127.0.0.1:8769/inject \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SESSION_ID","text":"[SUBCONSCIOUS ENGINE TEST] queue delivery","delivery":"queue"}'
```

Expect JSON with `"ok": true` and `"delivery": "queue"`. While Hermes is mid-turn, the message should **queue** (no interrupt); when idle, it should run immediately.

---

## 2. SubConscious-Engine — Hermes test checkout (pytest only)

Use a **separate clone** or branch for local verification **before** touching the live systemd service. Do not bind port 8770 from this checkout while the service is running.

```bash
cd /path/to/subconscious-engine-test   # NOT the systemd WorkingDirectory while service is up
git clone https://github.com/KarlitaHermes/SubConscious-Engine.git .  # first time only
git fetch origin
git checkout main
git pull origin main
git log -1 --oneline   # expect 96a4670 or newer

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q    # expect all tests pass (96+)
```

Config and state for the **live** server live under `~/.hermes/subconscious-engine/` (`config.yaml`, `state.yaml`). Do not wipe `state.yaml` unless intentionally resetting cooldowns.

---

## 3. SubConscious-Engine — systemd service upgrade (production server)

The live daemon runs as **`subconscious-engine.service`**. The shipped unit file uses:

| Setting | Value |
|---------|--------|
| Service name | `subconscious-engine` |
| WorkingDirectory | `/home/hermes/workspace/subconscious-engine` |
| ExecStart | `/home/hermes/workspace/subconscious-engine/.venv/bin/python -m src` |
| Config | `~/.hermes/subconscious-engine/config.yaml` (default) |
| State | `~/.hermes/subconscious-engine/state.yaml` |
| REST port | from config (default **8770**) |
| Logs | `journalctl -u subconscious-engine -f` and `~/.hermes/logs/` per config |

### 3.1 Check what is running now (old version)

```bash
systemctl status subconscious-engine
journalctl -u subconscious-engine -n 30 --no-pager

cd /home/hermes/workspace/subconscious-engine
git log -1 --oneline                    # note this commit for rollback
git fetch origin && git log -1 origin/main --oneline   # target: 96a4670+

curl -s http://127.0.0.1:8770/health || echo "health endpoint failed — very old build or service down"
```

**Signs you are on an old build:**

| Check | Old | New (`96a4670+`) |
|-------|-----|------------------|
| `git log -1` | before `62e0c9c` | `96a4670` or newer |
| `POST /ack` | missing or 404 | `200` with `{"ok":true,...}` |
| Inject while busy | interrupts current turn | queues (`delivery: "queue"`) |
| Duplicate nudge during cooldown / `in_progress` | may still inject | suppressed (notify gate) |
| Journal on startup | no `NotifyGate` / gate suppress logs | sources skip at DEBUG when gated |

Quick `/ack` probe:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -d '{"cooldown_key":"upgrade_probe","status":"in_progress"}'
# Expect 200 on new build; 404 or connection refused on old/missing
```

### 3.2 Upgrade the service checkout

**Do not** run `python -m src` manually on 8770 during this procedure. Only the systemd service should own that port.

```bash
cd /home/hermes/workspace/subconscious-engine

# Save rollback point
git rev-parse HEAD > /tmp/subconscious-engine-pre-upgrade.commit

git fetch origin
git checkout main
git pull origin main
git log -1 --oneline   # must show 96a4670 or newer

# Refresh venv dependencies (service uses this venv)
source .venv/bin/activate
pip install --upgrade pip
pip install aiohttp pyyaml
# optional dev install for pytest on this tree:
pip install -e ".[dev]"
python -m pytest -q
deactivate

# Reinstall unit file only if it changed (safe to re-run)
sudo cp systemd/subconscious-engine.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 3.3 Restart and verify

```bash
sudo systemctl restart subconscious-engine
sleep 2
systemctl status subconscious-engine

curl -s http://127.0.0.1:8770/health
# Expect: {"ok": true, "service": "subconscious-engine"}

curl -s -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -d '{"cooldown_key":"upgrade_probe","status":"done","cooldown_minutes":1}'
# Expect: {"ok": true, ...}

journalctl -u subconscious-engine -n 50 --no-pager | grep -E "listening|started|8770|error" || true
```

Confirm in logs:

- `SubConscious Engine started`
- `REST event source ... listening on 127.0.0.1:8770` (if inbound `http` entry point enabled)
- No traceback on startup

**Post-restart smoke inject** (via adapter, replace `SESSION_ID`):

```bash
curl -s -X POST http://127.0.0.1:8769/inject \
  -H "Content-Type: application/json" \
  -d '{"session_id":"SESSION_ID","text":"[SUBCONSCIOUS ENGINE TEST] post-upgrade systemd","delivery":"queue"}'
```

### 3.4 If the service fails to start

```bash
journalctl -u subconscious-engine -n 80 --no-pager
ls -la /home/hermes/workspace/subconscious-engine/.venv/bin/python
cat ~/.hermes/subconscious-engine/config.yaml   # syntax / paths
```

Common fixes:

- Recreate venv: `cd /home/hermes/workspace/subconscious-engine && python3 -m venv .venv && source .venv/bin/activate && pip install aiohttp pyyaml`
- Port 8770 in use: `ss -tlnp | grep 8770` — stop duplicate/manual process, not the service
- Config missing: `mkdir -p ~/.hermes/subconscious-engine && cp config.yaml.example ~/.hermes/subconscious-engine/config.yaml`

### 3.5 Rollback systemd engine only

```bash
cd /home/hermes/workspace/subconscious-engine
git checkout "$(cat /tmp/subconscious-engine-pre-upgrade.commit)"
sudo systemctl restart subconscious-engine
curl -s http://127.0.0.1:8770/health
```

---

## 4. Hermes skill & ack helper (use Hermes's own skills path)

User prefers Hermes-managed skills over `install-skill.sh` if you already maintain the skill elsewhere. Minimum: ensure the Agent knows the **two-step ack protocol** and can run `ack-engine.sh`.

From the engine repo (for the helper script only):

```bash
chmod +x /home/hermes/workspace/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh
```

Ack endpoint (default):

```bash
export SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770
# SUBCONSCIOUS_ENGINE_API_KEY=...   # only if config entry_points[].api_key is set
```

**Ack flow** (required for notify gate `in_progress` / cooldown behavior):

```bash
# When you start working on a nudge (parse cooldown_key from footer [engine-ack:KEY|in_progress,done])
/home/hermes/workspace/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh \
  COOLDOWN_KEY in_progress

# When finished
/home/hermes/workspace/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh \
  COOLDOWN_KEY done --minutes 60 --reset-idle   # --reset-idle for idle_engine / pending_decisions
```

---

## 5. Integration test plan (after adapter + systemd engine upgraded)

### A. Health

```bash
curl -s http://127.0.0.1:8770/health
curl -s http://127.0.0.1:8769/sessions | head
```

### B. Queue delivery while busy

1. Start a long Hermes task in a session.
2. Trigger a nudge (file drop, inbound POST, or wait for idle/weather if configured).
3. Confirm: **no interrupt**; nudge runs after the current turn.
4. Send `in_progress` then `done` acks for the nudge's `cooldown_key`.

### C. Notify gate — suppress redundant nudges

| Scenario | Expected |
|----------|----------|
| Same `cooldown_key` in cooldown | Engine does not inject again; log: `in cooldown` or DEBUG suppress |
| `ack-engine.sh KEY in_progress` | Same key blocked until `done` |
| HTTP poll item already seen | Not republished |
| Idle nudge while `idle_engine` in progress | No second idle inject |

Check engine logs:

```bash
journalctl -u subconscious-engine -f
# or file log from config logging.file under ~/.hermes/logs/
```

Set `logging.level: DEBUG` in config temporarily to see source-level suppressions; restart service after edit.

### D. File-drop smoke test

If directory entry point enabled; use a **fresh** `cooldown_key`:

```bash
mkdir -p ~/.hermes/subconscious-engine/events
cat > ~/.hermes/subconscious-engine/events/hermes-test.json <<'EOF'
{
  "text": "[SUBCONSCIOUS ENGINE TEST] notify gate smoke test",
  "event_type": "custom",
  "cooldown_key": "hermes_gate_test_1"
}
EOF
```

1. `ack-engine.sh hermes_gate_test_1 in_progress` after inject arrives.
2. Drop a second file with the same `cooldown_key` → should **not** inject.
3. `ack-engine.sh hermes_gate_test_1 done --minutes 60`.

---

## 6. Full rollback (adapter + engine)

**Adapter:**

```bash
cd /path/to/subconscious-adapter
git checkout 139af67
ln -sfn "$(pwd)" ~/.hermes/plugins/subconscious-adapter
sudo systemctl restart hermes-gateway
```

**Engine (systemd):**

```bash
cd /home/hermes/workspace/subconscious-engine
git checkout e84119f   # queue delivery, no notify gate
# or 6ae45cf for pre-queue
sudo systemctl restart subconscious-engine
```

---

## 7. Constraints (read first)

- **No changes** to `hermes-agent` repository.
- **Both repos** required for queue delivery; notify gate is **engine-only** (`96a4670+`).
- **One engine** on 8770 per host — the systemd service owns it after upgrade.
- Use throwaway `cooldown_key` values for tests (e.g. `hermes_gate_test_1`) so you do not block real idle/weather nudges.
- Injected messages include `[engine-ack:KEY|in_progress,done]` when `cooldown_key` is set — always ack both steps.
- **User approval:** run section 2 (pytest) and section 5 (integration) before section 3.3 restart in production if you upgraded a live system during business hours.

**Docs in repos:** `VERSION-NOTES.md` in each repo; full nudge reference in `hermes/subconscious-engine-nudges/SKILL.md`.
