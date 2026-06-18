#!/usr/bin/env bash
# Install or refresh Hermes skills from this repository.
#
# Usage:
#   ./hermes/install-skill.sh
#
# Installs:
#   ~/.hermes/skills/devops/subconscious-engine-nudges
#   ~/.hermes/skills/devops/subconscious-engine-config
#   ~/.hermes/skills/productivity/inbox-digest-curator
#
# Legacy symlink (older paths):
#   ~/.hermes/skills/subconscious-engine-nudges -> devops/subconscious-engine-nudges

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_ROOT="${HERMES_SKILLS_ROOT:-$HOME/.hermes/skills}"

install_skill() {
  local category="$1"
  local name="$2"
  local source="$REPO_ROOT/hermes/$name"
  local target="$SKILLS_ROOT/$category/$name"

  if [[ ! -f "$source/SKILL.md" ]]; then
    echo "Skill source not found: $source/SKILL.md" >&2
    exit 1
  fi

  mkdir -p "$(dirname "$target")"
  ln -sfn "$source" "$target"
  echo "  $target -> $source"
}

echo "Installing SubConscious Hermes skills..."
install_skill devops subconscious-engine-nudges
install_skill devops subconscious-engine-config
install_skill productivity inbox-digest-curator

if [[ -x "$REPO_ROOT/hermes/subconscious-engine-nudges/scripts/ack-engine.sh" ]]; then
  chmod +x "$REPO_ROOT/hermes/subconscious-engine-nudges/scripts/ack-engine.sh"
fi

# Legacy path used by some sessions
mkdir -p "$SKILLS_ROOT"
ln -sfn "$SKILLS_ROOT/devops/subconscious-engine-nudges" \
  "$SKILLS_ROOT/subconscious-engine-nudges"

echo ""
echo "Done. Optional ~/.hermes/.env:"
echo "  SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770"
echo ""
echo "Cron + inbox howto: docs/CRON-AND-INBOX.md"
echo "Test ack:"
echo "  $REPO_ROOT/hermes/subconscious-engine-nudges/scripts/ack-engine.sh idle_engine in_progress"
