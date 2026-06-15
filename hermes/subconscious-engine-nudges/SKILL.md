---
name: subconscious-engine-nudges
category: devops
description: >-
  Handle SubConscious Engine nudges injected into Hermes sessions — recognize each
  nudge type, spawn work, and POST /ack (in_progress + done) so idle detection and
  cooldowns stay correct. Install from the subconscious-engine repo.
---

# SubConscious Engine — Nudge Handling (Hermes)

Use this skill whenever a message in your session was **injected by SubConscious Engine** (not typed by Rev). These messages start with `[SUBCONSCIOUS` or `[SUBCONSCIOUS ENGINE` and may end with an ack footer.

This skill covers **every nudge type**, the **ack protocol**, and the **`ack-engine.sh` helper** shipped in this repository.

---

## 1. Install from the repository

Hermes should pull or sync the **subconscious-engine** repo, then install this skill:

```bash
# Clone or pull (adjust path if your checkout differs)
cd /home/hermes/workspace/subconscious-engine
git pull

# Install skill symlink into Hermes skills directory
chmod +x hermes/install-skill.sh hermes/subconscious-engine-nudges/scripts/ack-engine.sh
./hermes/install-skill.sh
```

Installed location: `~/.hermes/skills/devops/subconscious-engine-nudges` → repo `hermes/subconscious-engine-nudges/`.

**Optional env** in `~/.hermes/.env` (overrides config discovery):

```bash
SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770
SUBCONSCIOUS_ENGINE_API_KEY=          # only if entry_points[].api_key is set in engine config
SUBCONSCIOUS_CONFIG=~/.hermes/subconscious-engine/config.yaml
```

**Engine must be running** with an enabled `http` entry point (`type: http`, default port **8770**). The running instance needs a build that includes `POST /ack` (sync repo + restart engine after pull).

Verify:

```bash
curl -s http://127.0.0.1:8770/health
# {"ok": true, "service": "subconscious-engine"}
```

---

## 2. Architecture (what happens)

```
Entry points (idle | directory | http | http_poll)
  → EventBus → Router → SubConscious Adapter POST /inject
  → Hermes session (you see the message)
  → You POST /ack back to the engine (this skill)
```

- **Injection** uses adapter `http://127.0.0.1:8769/inject` — you do not call this; the engine does.
- **Acknowledgement** uses engine `http://127.0.0.1:8770/ack` — **you** call this via `ack-engine.sh` or `curl`.

Nudge types are **independent**. Each has its own `cooldown_key`. Working on `idle_engine` does not block `weather` or `pending_decisions` — ack each key separately.

---

## 3. Universal procedure (every real nudge)

Apply this to **every** subconscious nudge except test messages (section 10).

### Step A — Recognize

A subconscious injection usually:

- Starts with `[SUBCONSCIOUS` or `[SUBCONSCIOUS ENGINE`
- Was **not** typed by Rev in chat (adapter inject)
- Often ends with:

```
[engine-ack:COOLDOWN_KEY|in_progress,done]
```

Parse `COOLDOWN_KEY` = text between `engine-ack:` and `|`.

If there is **no footer**, use the fallback key from section 4 (event type or filename).

### Step B — Ack `in_progress` immediately

Before spawning a sub-agent or doing heavy work:

```bash
/path/to/subconscious-engine/hermes/subconscious-engine-nudges/scripts/ack-engine.sh \
  COOLDOWN_KEY in_progress
```

Or with optional event id:

```bash
ack-engine.sh idle_engine in_progress --event-id optional-uuid
```

**Effect:** counts as **activity** (idle timer resets even without Rev typing); blocks the **same** `cooldown_key` from firing again; does **not** start cooldown yet.

### Step C — Do the work

Follow the type-specific instructions in section 5. Prefer **one sub-agent per nudge** unless the prompt says otherwise.

### Step D — Ack `done` when finished

```bash
ack-engine.sh COOLDOWN_KEY done --minutes 60 --reset-idle
```

- `--minutes` — cooldown for that key (default: `idle.cooldown_minutes` from engine config, usually 60)
- `--reset-idle` — clears idle-period wake flag (recommended for idle-related keys)
- Weather polls often use `--minutes 360` (6 hours)

**Effect:** sets cooldown, clears in-progress, counts as activity.

### Step E — Report to Rev

Summarize what you did. Do not paste the full ack footer unless debugging.

---

## 4. Cooldown keys — how to find them

| Source | How to get `cooldown_key` |
|--------|---------------------------|
| Injected message footer | `[engine-ack:KEY\|in_progress,done]` → `KEY` |
| Idle maintenance / research | Always `idle_engine` (shared between both types) |
| Pending decisions wake nudge | `pending_decisions` |
| Open-Meteo weather | `open-meteo:<location>:<window>` e.g. `open-meteo:Warsaw, PL:2026-06-15T16:00` |
| Inbox file | `inbox:<filename>` e.g. `inbox:news-digest-2026-06-15.md` |
| Vault rule | `vault_rule:<rule_id>` from metadata in prompt |
| Custom HTTP / file drop | `cooldown_key` field if author set it; else use `event_type` |

**Router rule:** if the engine omitted `cooldown_key` on the event, the router uses `event_type` as the cooldown key — but the inject footer is only added when `cooldown_key` was set on the event. For footer-less messages, ack using the event type string (`alert`, `custom`, etc.).

---

## 5. Nudge types — what to do for each

### 5.1 Maintenance (`event_type: maintenance`, `cooldown_key: idle_engine`)

**When:** Rev idle ≥ threshold (default 30 min). Odd idle triggers alternate maintenance/research; maintenance is the odd cycles.

**Prompt signals:**

- `[SUBCONSCIOUS] System idle detected`
- Task file path: `{vault}/Projects/ORCHESTRATOR/Tasks/maintenance-tasks.md`
- Reports: `{vault}/Projects/ORCHESTRATOR/Reports`

**Your job:**

1. `ack-engine.sh idle_engine in_progress`
2. Spawn sub-agent:
   - Read maintenance-tasks.md
   - Check "Last done" / cooldown per task
   - Pick **one** due task; if none due → report "All tasks up to date" and stop
   - If due → execute, write report to Reports, update Last done in task file
3. `ack-engine.sh idle_engine done --minutes 60 --reset-idle`
4. Brief summary to Rev

**Do not** run kernel upgrades, Proxmox upgrades, or destructive ops without Rev's explicit approval.

---

### 5.2 Research (`event_type: research`, `cooldown_key: idle_engine`)

**When:** Idle cycle scheduled for research (even triggers) — same shared key as maintenance.

**Prompt signals:**

- `[SUBCONSCIOUS] System idle detected` + "self-improvement research"
- `{vault}/Projects/ORCHESTRATOR/Tasks/web-research-tasks.md`
- `{vault}/Projects/Dream-Journal`
- Reports directory

**Your job:**

1. `ack-engine.sh idle_engine in_progress` (same key as maintenance — only one idle nudge at a time per engine state)
2. Spawn sub-agent:
   - Check Reports for research in last **48h** — skip topics already covered
   - Pick **one** new topic from web-research-tasks or DREAM journal
   - Research thoroughly; write findings to Reports
   - Flag Rev only if genuinely interesting or urgent
3. `ack-engine.sh idle_engine done --minutes 60 --reset-idle`

If you already handled an idle nudge (`idle_engine` in progress or done recently), do not start duplicate work — ack done with a short "already handled" note if needed.

---

### 5.3 Pending decisions (`event_type: pending_decisions`, `cooldown_key: pending_decisions`)

**When:** Rev returns after an idle period (wake within `wake_grace_minutes`, default 10 min). Separate from maintenance/research.

**Prompt signals:**

- `[SUBCONSCIOUS] Rev has been idle for ~N minutes and just came back`
- Bullet list of items from recent Reports / Dream Backlog

**Your job:**

1. `ack-engine.sh pending_decisions in_progress`
2. Spawn sub-agent to evaluate each item:
   - **(a)** easy win — do it now
   - **(b)** needs Rev — one-liner summary for Rev
   - **(c)** already handled / not actionable — mark done
3. You review classifications and act (don't blindly spam Rev)
4. `ack-engine.sh pending_decisions done --minutes 60 --reset-idle`

**Decision markers** the engine scans for: `⚠️`, `needs decision`, `Rev to decide`, `for Rev:`, `should we`, `ACTION REQUIRED`.

---

### 5.4 Weather (`event_type: weather`, `cooldown_key: open-meteo:...`)

**When:** `http_poll` entry point with `response_format: open_meteo` (e.g. Warsaw 6-hour outlook every 6h).

**Prompt signals:**

- Weather summary, precipitation, ride/outdoors advisory
- Footer key like `open-meteo:Warsaw, PL:2026-06-15T16:00`

**Your job:**

1. `ack-engine.sh 'open-meteo:Warsaw, PL:2026-06-15T16:00' in_progress` (use exact key from footer)
2. Read the advisory; notify Rev only if:
   - Storm / heavy rain / urgent ride warning, or
   - Rev asked for weather updates
3. Otherwise a short "noted" is enough
4. `ack-engine.sh 'open-meteo:...' done --minutes 360` (match poll interval, typically 360 for 6h)

---

### 5.5 Inbox — notify (`event_type: inbox_notify`)

**When:** New file in vault `COMMS/Inbox` with notify disposition (e.g. `news-digest-*`, `research-digest-*`, `dream-session-*`, or frontmatter `priority: high`).

**Cooldown key:** `inbox:<filename>`

**Prompt signals:**

- `[SUBCONSCIOUS] New inbox file: <name>`
- Disposition: `notify`
- Content excerpt in message

**Your job:**

1. `ack-engine.sh inbox:FILENAME in_progress`
2. Review content; **notify Rev** with a concise summary and link/path
3. File to suggested vault destination if appropriate
4. `ack-engine.sh inbox:FILENAME done --minutes 60`

---

### 5.6 Inbox — delegate / review (`event_type: inbox_item`)

**Dispositions:** `delegate` (email-*, memory-*, routine) or `review` (unknown drops).

**Cooldown key:** `inbox:<filename>`

**Your job:**

1. `ack-engine.sh inbox:FILENAME in_progress`
2. Classify: notify Rev | file to vault | delegate to sub-agent | routine skip
3. Move/process per `Suggested vault destination` in prompt
4. `ack-engine.sh inbox:FILENAME done --minutes 60`

**Never process standing files:** `dream-task*.md`, `researcher-task.md`, `quick-wins-*`, `.processed`, `inbox.lock`.

---

### 5.7 Vault rules (`event_type: vault_rule`, `cooldown_key: vault_rule:<rule_id>`)

**When:** `vault_rules` directory entry point evaluates `rules.md` and a rule matches.

**Your job:**

1. Parse `rule_id` from footer or prompt metadata
2. `ack-engine.sh vault_rule:RULE_ID in_progress`
3. Follow the rule's prompt text (maintenance, checks, delegated tasks)
4. `ack-engine.sh vault_rule:RULE_ID done --minutes 60` (or rule-specific cooldown if configured)

---

### 5.8 Alerts (`event_type: alert`)

**When:** High-priority events (HTTP poll, file drop, inbound `POST /events`) with `priority ≥ 10` or explicit `event_type: alert`.

**Cooldown key:** from footer, or `alert`, or custom key in payload (e.g. `backup_check`).

**Your job:**

1. Ack `in_progress` with the correct key
2. Treat as **urgent** — investigate and notify Rev if action needed
3. Ack `done` with appropriate cooldown (often 60; critical recurring alerts may use longer)

---

### 5.9 Custom / broadcast / file-drop events

**Custom (`event_type: custom` or other):** Read the injected text literally. Ack using footer key or `event_type`. Follow instructions; default cooldown 60 minutes.

**Broadcast (`event_type: broadcast`):** May target multiple sessions. Same ack rules — use footer key or `broadcast`.

**Directory file drop** (`~/.hermes/subconscious-engine/events/`): JSON/YAML may include explicit `cooldown_key`. Text files use default event type only — ack with that type if no footer.

---

## 6. Multiple nudges at once

Independent keys can fire in parallel:

| Key A in progress | Key B can still fire? |
|-------------------|------------------------|
| `idle_engine` | Yes — e.g. `weather`, `pending_decisions` |
| `pending_decisions` | Yes — e.g. `idle_engine` |
| `inbox:foo.md` | Yes — different inbox files = different keys |

**Same key:** while `idle_engine` is `in_progress`, the engine **skips** another idle maintenance/research inject.

**Practical rule:** one sub-agent per nudge; ack each key on its own timeline. Do not merge unrelated nudges into one giant task unless Rev asks.

---

## 7. Helper script reference (`ack-engine.sh`)

Path in repo:

```
hermes/subconscious-engine-nudges/scripts/ack-engine.sh
```

**Examples:**

```bash
# Started work on idle nudge
ack-engine.sh idle_engine in_progress

# Finished idle work
ack-engine.sh idle_engine done --minutes 60 --reset-idle

# Weather (quote keys with spaces/colons)
ack-engine.sh 'open-meteo:Warsaw, PL:2026-06-15T16:00' done --minutes 360

# Override URL (rare)
ack-engine.sh idle_engine in_progress --url http://127.0.0.1:8771
```

**Raw curl equivalent:**

```bash
curl -s -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -d '{"cooldown_key":"idle_engine","status":"in_progress"}'
```

With API key:

```bash
curl -s -X POST http://127.0.0.1:8770/ack \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_KEY" \
  -d '{"cooldown_key":"idle_engine","status":"done","cooldown_minutes":60,"reset_idle_period":true}'
```

---

## 8. Discovering engine URL and auth (without guessing)

1. **Env:** `SUBCONSCIOUS_ENGINE_URL`, `SUBCONSCIOUS_ENGINE_API_KEY`
2. **Config:** `~/.hermes/subconscious-engine/config.yaml` — first enabled `entry_points[]` with `type: http`:
   - URL = `http://{host}:{port}`
   - API key = `api_key` (empty = no auth)
3. **Health check:** `GET {url}/health`
4. **Default if unset:** `http://127.0.0.1:8770`

The helper script reads config automatically when env is not set.

---

## 9. Config cross-reference (what the engine watches)

| Entry point `type` | Produces nudge types | Notes |
|--------------------|----------------------|-------|
| `idle` | maintenance, research, pending_decisions | Needs gateway + telegram session |
| `directory` + `handler: event_file` | custom, alert, … | Drop JSON/YAML in events dir |
| `directory` + `handler: inbox` | inbox_item, inbox_notify | Watches vault Inbox |
| `directory` + `handler: vault_rules` | vault_rule | Evaluates rules.md |
| `http` | anything POSTed to `/events` | Inbound API |
| `http_poll` | weather, alert, custom, … | Open-Meteo, remote feeds |

Routing rules in config map `event_type` → telegram (or other) delivery. See repo `config.yaml.example` and `README-AGENT.md`.

**Vault root** (for idle/inbox paths): `idle.vault_root` in config, typically `~/Documents/Obsidian Vault`.

---

## 10. Test nudges — special case

Messages containing **`[SUBCONSCIOUS ENGINE TEST]`**:

Rev's instruction: acknowledge receipt, show original message verbatim, **nothing else**.

1. Do **not** call `/ack` unless explicitly testing the ack flow
2. Do **not** spawn sub-agents or write reports
3. Reply briefly: received + quote original
4. When Rev says testing is over, resume normal procedure for real nudges

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `404` on `/ack` | Old engine build | Pull repo, restart subconscious-engine service |
| `401 Unauthorized` | `api_key` set in config | Pass `--api-key` or `SUBCONSCIOUS_ENGINE_API_KEY` |
| `cooldown_key is required` | Malformed body | Use `ack-engine.sh` with key as first arg |
| Idle keeps firing while you work | No `in_progress` ack | Call ack **before** long work |
| Same nudge type fires twice | No `done` ack | Call `done` when finished |
| Different nudge while busy | Expected | Independent keys — handle or defer separately |
| No `[engine-ack:...]` footer | Event had no `cooldown_key` | Ack using `event_type` or section 4 fallback |
| Connection refused :8770 | Engine down or wrong port | `systemctl status subconscious-engine`; check config port |

**State file** (read-only for debugging): `~/.hermes/subconscious-engine/state.yaml` — shows `cooldowns`, `tasks_in_progress`, `last_agent_handled`.

---

## 12. Related documentation in this repo

| File | Purpose |
|------|---------|
| `README-AGENT.md` | Install/start engine, config, `/ack` API details |
| `config.yaml.example` | Full config template |
| `hermes/install-skill.sh` | Install this skill into `~/.hermes/skills/` |
| `hermes/subconscious-engine-nudges/scripts/ack-engine.sh` | Ack helper |
| `ARCHITECTURE.md` | Internal engine design |

**Deprecated:** do not use `~/.hermes/subconscious-engine/ack.yaml` file-based ack — use `POST /ack` instead.

---

## 13. Quick checklist (print in your head)

```
[ ] Subconscious injection recognized
[ ] cooldown_key parsed from footer (or fallback)
[ ] ack-engine.sh KEY in_progress
[ ] Type-specific work (section 5)
[ ] ack-engine.sh KEY done [--minutes N] [--reset-idle]
[ ] Short summary to Rev
```
