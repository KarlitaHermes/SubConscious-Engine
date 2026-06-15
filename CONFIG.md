# SubConscious Engine — Configuration Reference

## config.yaml

```yaml
# SubConscious Engine Configuration

# Gateway connection
gateway:
  url: "http://127.0.0.1:8642"
  api_key: ""  # API_SERVER_KEY from ~/.hermes/.env (auto-loaded if empty)

# SubConscious Adapter connection
adapter:
  url: "http://127.0.0.1:8769"

# Idle detection
idle:
  # How long to wait before considering a session idle (minutes)
  threshold_minutes: 30
  # Minimum time between triggers (minutes)
  cooldown_minutes: 60
  # Which session source to target (telegram, cli, etc.)
  target_source: "telegram"
  # Fallback sources if primary not available
  fallback_sources: ["cli"]

# Logging
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  file: "~/.hermes/logs/subconscious-engine.log"
  max_bytes: 10485760  # 10MB
  backup_count: 3

# State file
state:
  file: "~/.hermes/subconscious-engine/state.yaml"
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `API_SERVER_KEY` | Gateway REST API key (from `~/.hermes/.env`) |
| `SUBCONSCIOUS_URL` | Override adapter URL |
| `GATEWAY_URL` | Override gateway URL |

## State File Format

The engine stores its state in a simple YAML file:

```yaml
# ~/.hermes/subconscious-engine/state.yaml
last_trigger: 1781458800.0  # Unix timestamp
trigger_count: 5
last_target_session: "20260615_075357_b969b9f4"
last_delivery_status: "ok"  # ok, failed, skipped
```

## systemd Service

The engine runs as a systemd service:

```bash
# Install
sudo cp systemd/subconscious-engine.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable subconscious-engine
sudo systemctl start subconscious-engine

# Check status
systemctl status subconscious-engine
journalctl -u subconscious-engine -f

# Stop
sudo systemctl stop subconscious-engine
```
