#!/usr/bin/env bash
# Install or refresh Hermes skills from this repository.
#
# Hermes trusts real files under ~/.hermes/skills/. Symlinks into a git
# checkout resolve outside that tree and are rejected — so we copy.
#
# Usage:
#   ./hermes/install-skill.sh
#
# Installs (copies):
#   ~/.hermes/skills/devops/subconscious-engine-nudges
#   ~/.hermes/skills/devops/subconscious-engine-config
#   ~/.hermes/skills/productivity/inbox-digest-curator
#   ~/.hermes/skills/productivity/kanban-se-bridge
#
# Legacy path (also a real copy):
#   ~/.hermes/skills/subconscious-engine-nudges

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
  # Drop prior symlink or mixed dir (nested symlink leftovers from old installer)
  rm -rf "$target"
  mkdir -p "$target"
  cp -a "$source"/. "$target"/
  # Ensure helpers are executable in the install tree
  if [[ -f "$target/scripts/ack-engine.sh" ]]; then
    chmod +x "$target/scripts/ack-engine.sh"
  fi
  echo "  $target (copied)"
}

echo "Installing SubConscious Hermes skills (copy, not symlink)..."
install_skill devops subconscious-engine-nudges
install_skill devops subconscious-engine-config
install_skill productivity inbox-digest-curator
install_skill productivity kanban-se-bridge

# Legacy path used by some sessions — real copy so trust resolves under skills root
legacy="$SKILLS_ROOT/subconscious-engine-nudges"
rm -rf "$legacy"
mkdir -p "$legacy"
cp -a "$REPO_ROOT/hermes/subconscious-engine-nudges"/. "$legacy"/
if [[ -f "$legacy/scripts/ack-engine.sh" ]]; then
  chmod +x "$legacy/scripts/ack-engine.sh"
fi
echo "  $legacy (copied, legacy path)"

echo ""
echo "Done. Reload skills in Hermes (/reload-skills) or restart hermes-gateway."
echo "Optional ~/.hermes/.env:"
echo "  SUBCONSCIOUS_ENGINE_URL=http://127.0.0.1:8770"
echo ""
echo "Cron + inbox howto: docs/CRON-AND-INBOX.md"
echo "Kanban → SE return: docs/KANBAN-AND-SE.md"
echo "Test ack:"
echo "  $SKILLS_ROOT/devops/subconscious-engine-nudges/scripts/ack-engine.sh idle_engine in_progress"
