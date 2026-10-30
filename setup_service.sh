#!/usr/bin/env bash
# Creates a systemd user unit for the power logger so it runs on boot.
# Call from install.sh or run manually: ./setup_service.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Prefer venv Python when install.sh passes it; otherwise fallback
PYTHON="${PYTHON:-$SCRIPT_DIR/.venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
    PYTHON="python3"
fi
UNIT_NAME="system-monitor-power"
SERVICE_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${UNIT_NAME}.service"
CONFIG_DIR="$(dirname "$SERVICE_FILE")"

mkdir -p "$CONFIG_DIR"
cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=System Monitor Power Logger (CPU RAPL + GPU)
After=network.target

[Service]
Type=simple
ExecStart=$PYTHON $SCRIPT_DIR/power_logger.py
Restart=on-failure
RestartSec=60

[Install]
WantedBy=default.target
SERVICEEOF
echo "Created: $SERVICE_FILE"
systemctl --user daemon-reload
systemctl --user enable "$UNIT_NAME"
systemctl --user start "$UNIT_NAME" 2>/dev/null || true
echo "Service enabled and started. Check: systemctl --user status $UNIT_NAME"
