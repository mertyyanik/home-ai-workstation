#!/usr/bin/env bash
# Run the status panel as a systemd service in WSL Ubuntu, so it starts with Ubuntu.
# The service runs as your normal user, not root. Safe to run again.
#
#   sudo bash scripts/setup-panel-service.sh
#
# To remove it: sudo systemctl disable --now aiws-panel
#               sudo rm /etc/systemd/system/aiws-panel.service
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo 'ERROR: Run with sudo: sudo bash scripts/setup-panel-service.sh' >&2
  exit 1
fi
user="${SUDO_USER:-}"
if [[ -z "$user" || "$user" == root ]]; then
  echo 'ERROR: Run through sudo from your normal Ubuntu user.' >&2
  exit 1
fi
if [[ "$(cat /proc/1/comm)" != systemd ]]; then
  echo 'ERROR: systemd is not running in this distribution. Enable it in /etc/wsl.conf.' >&2
  exit 1
fi

repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
port="${AIWS_PANEL_PORT:-8088}"
unit=/etc/systemd/system/aiws-panel.service

cat > "$unit" <<EOF
# Managed by home-ai-workstation scripts/setup-panel-service.sh
[Unit]
Description=Home AI Workstation status panel
After=network.target
StartLimitIntervalSec=0

[Service]
User=$user
WorkingDirectory=$repository
Environment=AIWS_PANEL_PORT=$port
ExecStart=/usr/bin/bash scripts/aiws.sh panel
Restart=always
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
chmod 644 "$unit"

systemctl daemon-reload
systemctl enable aiws-panel >/dev/null 2>&1
systemctl restart aiws-panel

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if ss -ltn | grep -q "127.0.0.1:$port "; then
    echo "OK: Status panel service runs on http://localhost:$port as $user."
    exit 0
  fi
  sleep 1
done
echo 'ERROR: The panel did not start. Check: journalctl -u aiws-panel -n 30' >&2
exit 1
