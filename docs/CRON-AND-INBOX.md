# Cron jobs and the SubConscious inbox pipeline

How Hermes **cron jobs** feed the **SubConscious Engine** (SE) instead of messaging the human directly. Sanitized from a live deployment reference — no real job IDs, emails, or vault paths.

**Related:**

- Engine classification: `src/checks/inbox.py`
- Inbox entry point: `src/sources/inbox_watcher.py`
- Hermes skills: `hermes/inbox-digest-curator/`, `hermes/subconscious-engine-nudges/`
- Config example: `examples/working-deployment/engine-config.production.yaml` (inbox enabled)

---

## Principle

**No cron job should deliver directly to the human** (`deliver: "origin"` / Telegram inject from cron is forbidden for routine output).

Use **`deliver: "local"`** (or equivalent) so cron output becomes **files on disk**. The SE **inbox watcher** picks them up and nudges the Hermes agent. The agent curates, files to the vault, and notifies the User when needed.

```
Cron job runs
    → writes *.md to vault COMMS/Inbox/  (or ~/.hermes/cron/output/)
        ↓
SE inbox watcher (directory entry point, ~30s poll)
    → classify_inbox_file() in src/checks/inbox.py
        ↓
NotifyGate + Router
    → POST adapter :8769/inject  (delivery: queue)
        ↓
Hermes agent receives [SUBCONSCIOUS] New inbox file: …
    → ack in_progress → curate/delegate → ack done
        ↓
Summary to the User (notify) or silent filing (routine)
```

Weather is **not** a cron concern anymore — use SE `http_poll` with `response_format: open_meteo` (`weather_example` in working examples).

---

## Engine config (inbox entry point)

Enable a directory entry point on your vault inbox (paths are placeholders):

```yaml
entry_points:
  - id: inbox
    type: directory
    enabled: true
    path: ~/path/to/your/obsidian-vault/COMMS/Inbox
    poll_interval_seconds: 30
    handle:
      handler: inbox
      default_event_type: inbox_item
      default_priority: 0

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

Copy the full production-shaped file from `examples/working-deployment/engine-config.production.yaml` (includes inbox + idle + weather_example).

---

## Filename conventions (engine-side)

The engine assigns **disposition** from filename prefix (see `src/checks/inbox.py`):

| Prefix | Disposition | `event_type` | Typical agent action |
|--------|-------------|--------------|----------------------|
| `news-digest-` | notify | `inbox_notify` | Delegate curation → notify User |
| `research-digest-` | notify | `inbox_notify` | Delegate curation → notify User |
| `dream-session-` | notify | `inbox_notify` | Summarize ideas |
| `email-` | delegate | `inbox_item` | **Main session** — security-sensitive |
| `memory-`, `knowledge-graph-` | delegate | `inbox_item` | File to vault, brief OK |
| YAML frontmatter `priority: high` | notify | `inbox_notify` | Always notify |

**Skipped (never processed):** `dream-task*.md`, `researcher-task.md`, `quick-wins-*`, `.processed`, `inbox.lock`.

**Vault destinations** (relative to `idle.vault_root`):

| Prefix | Folder |
|--------|--------|
| `news-digest-` | `Projects/News-Digests/` |
| `research-digest-` | `Projects/Research/` |
| `dream-session-` | `Projects/Dream-Journal/` |
| `knowledge-graph-`, `memory-*` | `Technical/` |
| default | `Projects/Inbox-Processed/` |

---

## Hermes cron jobs (patterns)

Configure jobs in Hermes with **`deliver: local`** and a script that **writes markdown** into `COMMS/Inbox/` (or a path the inbox watcher reads).

### Example job categories

| Category | Example schedule | Output file pattern | Notes |
|----------|------------------|---------------------|--------|
| News digest | Daily 05:00 | `news-digest-YYYY-MM-DD.md` | Research headlines → inbox |
| Research digest | Every 2 days | `research-digest-*.md` | Portfolio / deep research |
| Email fetch | Every 5 min | `email-<timestamp>-<subject-slug>.md` | Use trusted-sender + 2FA rules in skill |
| Dream session | Daily 03:10 | `dream-session-YYYY-MM-DD.md` | Idea extraction |
| Vault hygiene | Weekly | `vault-hygiene-*.md` | Cleanup report |
| Backup verify | Daily | `backup-verify-*.md` | Integrity check |
| System health | Every 30 min | optional alert files | Prefer watchdog → SE only on failure |
| **SE watchdog** | Every 5 min | (no inbox file) | Restarts `subconscious-engine.service` if down |

Do **not** copy production job UUIDs into git — create jobs in your Hermes instance and point scripts at your inbox path.

### Example cron script contract

```bash
#!/usr/bin/env bash
# ~/.hermes/scripts/write-news-digest.sh — invoked by Hermes cron (deliver: local)
set -euo pipefail
INBOX="${VAULT_ROOT:-$HOME/path/to/your/obsidian-vault}/COMMS/Inbox"
DATE="$(date +%Y-%m-%d)"
OUT="$INBOX/news-digest-${DATE}.md"

mkdir -p "$INBOX"
cat > "$OUT" <<EOF
---
source: news-digest-cron
generated: ${DATE}
---

# News digest ${DATE}

(body written by your fetch logic)
EOF
```

Within ~30s the SE inbox watcher should log classification and inject a nudge.

---

## Agent workflow (skills)

Install from this repo:

```bash
./hermes/install-skill.sh
```

| Skill | Role |
|-------|------|
| `subconscious-engine-nudges` | ACK protocol, all nudge types |
| `subconscious-engine-config` | Edit `config.yaml`, restart engine, tuning |
| `inbox-digest-curator` | What to do when inbox nudge arrives |

**Inbox nudge flow:**

1. `ack-engine.sh inbox:FILENAME in_progress`
2. **News / research / dream** → sub-agent (`background=true`) to read file, curate, file to vault
3. **Email** → main session only; verify actionable content with the User before acting (email spoofing)
4. **Routine** → file to vault, short confirmation
5. `ack-engine.sh inbox:FILENAME done --minutes 60`

---

## Email security (summary)

Configure a **trusted personal sender** in your environment (never commit the address). For `email-*.md` files:

- **Actionable** content (links, attachments, instructions) → confirm with the User on Telegram before acting
- **Casual** FYI → summarize and file

Full rules: `hermes/inbox-digest-curator/SKILL.md`.

---

## Verification

```bash
# Engine up
curl -s http://127.0.0.1:8770/health

# Drop a synthetic inbox file
mkdir -p ~/path/to/your/obsidian-vault/COMMS/Inbox
echo "# test" > ~/path/to/your/obsidian-vault/COMMS/Inbox/news-digest-$(date +%F)-test.md

# Watch logs
journalctl -u subconscious-engine -f
# or: tail -f ~/.hermes/logs/subconscious-engine.log
```

Expect: classification `notify`, inject with `cooldown_key: inbox:news-digest-…`, agent receives `[SUBCONSCIOUS] New inbox file:`.

---

## Anti-patterns

- Cron with `deliver: "origin"` for digests that should be curated
- Two SE processes on port 8770
- Skipping `in_progress` ack (notify gate may re-fire)
- Delegating **email** handling to a sub-agent
- Committing live `config.yaml`, `state.yaml`, or Gmail credentials
