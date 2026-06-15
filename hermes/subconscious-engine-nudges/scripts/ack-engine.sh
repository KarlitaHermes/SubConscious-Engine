#!/usr/bin/env bash
# Tell SubConscious Engine that Hermes started or finished handling a nudge.
#
# Usage:
#   ack-engine.sh COOLDOWN_KEY in_progress
#   ack-engine.sh COOLDOWN_KEY done [--minutes 60] [--reset-idle] [--event-id ID]
#
# Environment (optional — otherwise read from engine config):
#   SUBCONSCIOUS_ENGINE_URL      e.g. http://127.0.0.1:8770
#   SUBCONSCIOUS_ENGINE_API_KEY  Bearer token when entry_points[].api_key is set
#   SUBCONSCIOUS_CONFIG          default ~/.hermes/subconscious-engine/config.yaml

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${SUBCONSCIOUS_CONFIG:-$HOME/.hermes/subconscious-engine/config.yaml}"

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

if [[ $# -lt 1 ]]; then
  usage 1
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage 0
fi

if [[ $# -lt 2 ]]; then
  usage 1
fi

COOLDOWN_KEY="$1"
STATUS="$(echo "$2" | tr '[:upper:]' '[:lower:]')"
shift 2

MINUTES=""
RESET_IDLE="false"
EVENT_ID=""
BASE_URL="${SUBCONSCIOUS_ENGINE_URL:-}"
API_KEY="${SUBCONSCIOUS_ENGINE_API_KEY:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --minutes)
      MINUTES="$2"
      shift 2
      ;;
    --reset-idle)
      RESET_IDLE="true"
      shift
      ;;
    --event-id)
      EVENT_ID="$2"
      shift 2
      ;;
    --url)
      BASE_URL="$2"
      shift 2
      ;;
    --api-key)
      API_KEY="$2"
      shift 2
      ;;
    -h|--help)
      usage 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage 1
      ;;
  esac
done

if [[ "$STATUS" != "in_progress" && "$STATUS" != "done" && "$STATUS" != "completed" ]]; then
  echo "STATUS must be in_progress, done, or completed (got: $STATUS)" >&2
  exit 1
fi

if [[ -z "$BASE_URL" || -z "$API_KEY" ]]; then
  if [[ ! -f "$CONFIG_PATH" ]]; then
    if [[ -z "$BASE_URL" ]]; then
      echo "Config not found: $CONFIG_PATH — set SUBCONSCIOUS_ENGINE_URL" >&2
      exit 1
    fi
  else
    # shellcheck disable=SC2016
    read -r CFG_URL CFG_KEY CFG_MINUTES < <(python3 - "$CONFIG_PATH" <<'PY'
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("  ", "", "60")
    sys.exit(0)

path = Path(sys.argv[1])
data = yaml.safe_load(path.read_text()) or {}
url = ""
api_key = ""
minutes = str((data.get("idle") or {}).get("cooldown_minutes", 60))

for ep in data.get("entry_points") or []:
    if ep.get("type") == "http" and ep.get("enabled", True):
        host = ep.get("host") or "127.0.0.1"
        port = ep.get("port") or 8770
        url = f"http://{host}:{port}"
        api_key = ep.get("api_key") or ""
        break

print(url, api_key, minutes)
PY
)
    [[ -z "$BASE_URL" && -n "$CFG_URL" ]] && BASE_URL="$CFG_URL"
    [[ -z "$API_KEY" && -n "$CFG_KEY" ]] && API_KEY="$CFG_KEY"
    [[ -z "$MINUTES" && -n "$CFG_MINUTES" ]] && MINUTES="$CFG_MINUTES"
  fi
fi

if [[ -z "$BASE_URL" ]]; then
  BASE_URL="http://127.0.0.1:8770"
fi

if [[ -z "$MINUTES" ]]; then
  MINUTES="60"
fi

BASE_URL="${BASE_URL%/}"
ACK_URL="${BASE_URL}/ack"

JSON_BODY="$(python3 - "$COOLDOWN_KEY" "$STATUS" "$MINUTES" "$RESET_IDLE" "$EVENT_ID" <<'PY'
import json
import sys

key, status, minutes, reset_idle, event_id = sys.argv[1:6]
body = {"cooldown_key": key, "status": status}
if status != "in_progress":
    body["cooldown_minutes"] = int(minutes)
    if reset_idle.lower() == "true":
        body["reset_idle_period"] = True
if event_id:
    body["event_id"] = event_id
print(json.dumps(body))
PY
)"

CURL_ARGS=(-sS -X POST "$ACK_URL" -H "Content-Type: application/json" -d "$JSON_BODY" -w "\n%{http_code}")
if [[ -n "$API_KEY" ]]; then
  CURL_ARGS+=(-H "Authorization: Bearer ${API_KEY}")
fi

RESPONSE="$(curl "${CURL_ARGS[@]}")"
HTTP_CODE="$(echo "$RESPONSE" | tail -n1)"
BODY="$(echo "$RESPONSE" | sed '$d')"

if [[ "$HTTP_CODE" -ge 200 && "$HTTP_CODE" -lt 300 ]]; then
  echo "$BODY"
  exit 0
fi

echo "ack-engine: POST $ACK_URL failed (HTTP $HTTP_CODE)" >&2
echo "$BODY" >&2
exit 1
