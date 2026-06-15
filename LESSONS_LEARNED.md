# SubConscious Engine — Lessons Learned from Old Orchestrator

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

### 4. Keep the Engine Stateless Where Possible
**Problem:** The old orchestrator had complex state management with decisions queues, goals trackers, etc.
**Solution:** Minimal state — just cooldown timestamps and last trigger times. Store in a simple YAML file.

## Code Lessons

### 5. Don't Over-Engineer the Idle Detection
**Problem:** The old idle engine had multiple config options, alternating maintenance/research prompts, etc.
**Solution:** Simple idle detection: check last user activity timestamp. If idle > threshold, trigger. One prompt type.

### 6. Don't Block the Main Loop
**Problem:** The old orchestrator's main loop could block on long-running operations.
**Solution:** All HTTP calls use async with timeouts. The main loop never blocks.

### 7. Don't Hardcode Platform-Specific Logic
**Problem:** The old orchestrator had Telegram-specific code (TelegramSender, batcher, etc.).
**Solution:** The engine is platform-agnostic. It injects via SubConscious Adapter, which routes to the correct platform. The engine doesn't know or care about Telegram/Discord/etc.

### 8. Don't Use Complex IPC Mechanisms
**Problem:** We tried Unix sockets, WebSocket, direct DB access, message queues...
**Solution:** Simple HTTP REST API. `GET /sessions` to list, `POST /inject` to send. That's it.

## Deployment Lessons

### 9. Use systemd for Service Management
**Problem:** Running the orchestrator manually or via cron was unreliable.
**Solution:** Proper systemd unit file with `Restart=on-failure`, logging, and clean start/stop.

### 10. Keep Config Separate from Code
**Problem:** Config was scattered across multiple files.
**Solution:** Single `config.yaml` with all options. Example config shipped as `config.yaml.example`.

### 11. Don't Install in the Gateway's Directory
**Problem:** The old orchestrator lived in `~/.hermes/orchestrator/` which is inside the gateway's home.
**Solution:** The engine lives in its own directory. The plugin is in `~/.hermes/plugins/subconscious-adapter/`. Clean separation.

## Testing Lessons

### 12. Test the Delivery Mechanism Independently
**Problem:** We couldn't test injection without a running gateway.
**Solution:** The SubConscious Adapter has its own test suite. The engine's delivery module can be tested with a mock HTTP server.

### 13. Don't Test Against Production
**Problem:** Early tests injected messages into real Telegram sessions.
**Solution:** Use a dedicated test session. Never test against Rev's main session.
