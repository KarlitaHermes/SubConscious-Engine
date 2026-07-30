# SubConscious Engine — Lessons Learned from Legacy Automation

## Architecture Lessons

### 1. Don't Modify the Gateway
**Problem:** We modified `gateway/run.py` directly to wire in the idle engine. When Hermes updated, changes were lost.
**Solution:** Use the plugin system. The SubConscious Adapter is a registered platform adapter. The engine communicates with it via REST API. Zero gateway code modification.

### 2. Don't Use Unix Sockets for IPC
**Problem:** The old `SocketIPCClient` used a Unix socket (`hermes-agent.sock`) that stopped working after a gateway update.
**Solution:** Use HTTP REST API. The SubConscious Adapter exposes `GET /sessions` and `POST /inject`. HTTP is stable, debuggable, and survives gateway updates.

### 3. Don't Store State in the Gateway's DB
**Problem:** We tried to write directly to `state.db` to inject messages. The gateway's schema changed and broke our code.
**Solution:** The engine manages its own state file (`~/.hermes/subconscious-engine/state.yaml`). The gateway's DB is read-only (via REST API).

### 4. Keep State Boring and Local
**Problem:** The previous subsystem had complex state management with decisions queues, goals trackers, etc.
**Solution:** One engine-owned YAML file. Grow keys only when needed (cooldowns, acks, dedupe, nudge budget) — never the gateway DB or a second datastore.

## Code Lessons

### 5. Keep Idle Detection Simple; Layer Behavior in Events
**Problem:** The old idle engine buried scheduling and prompt variety in one opaque loop.
**Solution:** Idle remains “activity older than threshold → publish an event.” Alternating maintenance/research and pending-decisions wake nudges are just different event types + routing/acks — not a separate scheduler service.

### 6. Don't Block the Consume Loop
**Problem:** The legacy daemon's main loop could block on long-running operations.
**Solution:** Async HTTP with timeouts; sources and the bus consumer catch errors and continue. Never block the loop on agent work — inject and return.

### 7. Don't Hardcode Platform-Specific Logic
**Problem:** The legacy daemon had Telegram-specific code (TelegramSender, batcher, etc.).
**Solution:** The engine is platform-agnostic. It injects via SubConscious Adapter, which routes to the correct platform. The engine doesn't know or care about Telegram/Discord/etc.

### 8. Don't Use Complex IPC Mechanisms
**Problem:** We tried Unix sockets, WebSocket, direct DB access, message queues...
**Solution:** Plain HTTP. Adapter: `GET /sessions`, `POST /inject`. Engine ingress: `POST /events`, `POST /ack`. No sockets, no shared DB writes.

## Deployment Lessons

### 9. Use systemd for Service Management
**Problem:** Running the legacy daemon manually or via cron was unreliable.
**Solution:** Proper systemd unit file with `Restart=on-failure`, logging, and clean start/stop.

### 10. Keep Config Separate from Code
**Problem:** Config was scattered across multiple files.
**Solution:** Single `config.yaml` with all options. Example config shipped as `config.yaml.example`.

### 11. Don't Install in the Gateway's Directory
**Problem:** The legacy automation lived inside the gateway home directory instead of its own tree.
**Solution:** The engine lives in its own directory. The plugin is in `~/.hermes/plugins/subconscious-adapter/`. Clean separation.

## Testing Lessons

### 12. Test the Delivery Mechanism Independently
**Problem:** We couldn't test injection without a running gateway.
**Solution:** The SubConscious Adapter has its own test suite. The engine's delivery module can be tested with a mock HTTP server.

### 13. Don't Test Against Production
**Problem:** Early tests injected messages into real Telegram sessions.
**Solution:** Use a dedicated test session. Never test against User's main session.
