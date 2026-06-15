# SubConscious Engine — TODO

## Deferred

### CLI session injection (adapter fix)

**Status:** Deferred — address later, not blocking v1 engine.

**Problem:** `POST /inject` to a `cli` source session fails with:

```json
{"error": "'cli' is not a valid Platform"}
```

**Cause:** SubConscious Adapter's `state.db` fallback in `_lookup_session_origin()` constructs `Platform("cli")`, but `cli` is not a registered `Platform` enum member in Hermes Gateway (`gateway/config.py`). Telegram and other platform enums work; CLI does not.

**Observed:** Tested against session `20260615_113428_e7f813` (source: `cli`) — inject returned 500. Telegram session `20260615_075357_b969b9f4` inject succeeded.

**Impact on engine:** `config.yaml` `idle.fallback_sources: ["cli"]` will not work until fixed. Engine v1 should target `telegram` only and log a warning when CLI fallback is skipped.

**Fix location:** `~/.hermes/plugins/subconscious-adapter/__init__.py` — map `cli` sessions to a valid platform (e.g. `Platform.LOCAL`) or register CLI as a plugin platform before dispatch.

## Architecture (v1 scaffold)

- Async event router: sources → `EventBus` → `Router` → multi-session delivery
- Sources: file drop dir, inbound REST (`:8770`), idle poller
- Target resolution: rules + optional hints on event (not mandatory)
- External REST polling (outbound) — later
- Idle: maintenance/research alternation + pending-decisions wake nudge
- `src/checks/` — vault file scanning (decisions, inbox classification, rules.md evaluation)

## Testing guidelines

**Do not trigger real agent work during integration tests.** Injected messages run the full Hermes agent in the target session. Even harmless-looking test text can cause long-running tasks (e.g. vault cleanup, maintenance sub-agents).

For live tests until session is free:
- Use **test profile**: `python -m src --config config.test.yaml` (idle OFF, port 8771, separate state/logs)
- Prefer **mocked HTTP** in pytest (no real inject)
- If a live inject is required: use a **dedicated test session**, not Rev's main Telegram session
- Keep test message text clearly marked `[SUBCONSCIOUS ENGINE TEST]` and **do not** reference maintenance task files or open-ended instructions
- **Disable idle source** in test config (`sources.idle: false`) to avoid maintenance prompts on startup
- Wait for user confirmation before further live Telegram tests
