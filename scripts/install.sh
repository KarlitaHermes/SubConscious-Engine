#!/bin/bash
# SubConscious Engine — Install Script

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="$HOME/workspace/subconscious-engine"
CONFIG_DIR="$HOME/.hermes/subconscious-engine"
LOG_DIR="$HOME/.hermes/logs"

echo "=== SubConscious Engine Installer ==="

# 1. Create directories
echo "Creating directories..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

# 2. Create virtual environment
echo "Creating virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install aiohttp pyyaml

# 3. Copy config if not exists
if [ ! -f "$CONFIG_DIR/config.yaml" ]; then
    echo "Creating default config..."
    cp "$INSTALL_DIR/config.yaml.example" "$CONFIG_DIR/config.yaml"
    echo "Edit $CONFIG_DIR/config.yaml to customize."
fi

# 4. Install systemd service
echo "Installing systemd service..."
sudo cp "$INSTALL_DIR/systemd/subconscious-engine.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable subconscious-engine

echo ""
echo "=== Installation Complete ==="
echo ""
echo "Start:  sudo systemctl start subconscious-engine"
echo "Stop:   sudo systemctl stop subconscious-engine"
echo "Status: systemctl status subconscious-engine"
echo "Logs:   journalctl -u subconscious-engine -f"
echo ""
echo "Config: $CONFIG_DIR/config.yaml"
