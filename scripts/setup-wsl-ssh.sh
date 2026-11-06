#!/usr/bin/env bash
# Set up a key-only OpenSSH server in WSL Ubuntu, reachable only through loopback.
# Windows Tailscale forwards tailnet traffic to it, so it needs no public port.
#
#   sudo bash scripts/setup-wsl-ssh.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo 'ERROR: Run with sudo: sudo bash scripts/setup-wsl-ssh.sh' >&2
  exit 1
fi
user="${SUDO_USER:-}"
if [[ -z "$user" || "$user" == root ]]; then
  echo 'ERROR: Run through sudo from your normal Ubuntu user.' >&2
  exit 1
fi
port="${AIWS_SSH_PORT:-2222}"
config=/etc/ssh/sshd_config.d/10-aiws.conf

apt-get update
apt-get install -y openssh-server

cat > "$config" <<EOF
# Managed by home-ai-workstation scripts/setup-wsl-ssh.sh
Port $port
ListenAddress 127.0.0.1
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
AllowUsers $user
EOF
chmod 644 "$config"

mkdir -p /run/sshd
sshd -t

home="$(getent passwd "$user" | cut -d: -f6)"
install -d -m 700 -o "$user" -g "$user" "$home/.ssh"
if [[ ! -e "$home/.ssh/authorized_keys" ]]; then
  install -m 600 -o "$user" -g "$user" /dev/null "$home/.ssh/authorized_keys"
fi

# Recent Ubuntu releases start OpenSSH through a socket generated from this config.
systemctl daemon-reload
if systemctl cat ssh.socket >/dev/null 2>&1; then
  systemctl enable ssh.socket
  systemctl restart ssh.socket
else
  systemctl enable ssh
  systemctl restart ssh
fi

if ss -ltn | grep -q "127.0.0.1:$port "; then
  echo "OK: OpenSSH listens on 127.0.0.1:$port, key login only, user $user."
else
  echo "ERROR: OpenSSH is not listening on 127.0.0.1:$port." >&2
  exit 1
fi
