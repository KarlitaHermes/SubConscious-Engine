#!/usr/bin/env bash
# Install or refresh the Hermes skill from this repository.
#
# Usage:
#   ./hermes/install-skill.sh
#   ./hermes/install-skill.sh /custom/target/path

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$REPO_ROOT/hermes/subconscious-engine-nudges"
TARGET="${1:-$HOME/.hermes/skills/devops/subconscious-engine-nudges}"

if [[ ! -f "$SOURCE/SKILL.md" ]]; then
  echo "Skill source not found: $SOURCE/SKILL.md" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
ln -sfn "$SOURCE" "$TARGET"
chmod +x "$SOURCE/scripts/ack-engine.sh"

echo "Installed subconscious-engine-nudges skill:"
echo "  $TARGET -> $SOURCE"
echo ""
echo "Optional: add to ~/.hermes/.env"
echo "  SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770"
echo ""
echo "Helper script:"
echo "  $SOURCE/scripts/ack-engine.sh idle_engine in_progress"
