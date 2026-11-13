#!/usr/bin/env bash
#
# UniDocs server installer (Linux, Debian/Ubuntu).
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/Lukas-dev-de/UniDocs/main/installer/install-server.sh | bash
#
# Installs the self-hosted server (web UI + sync API) as a systemd service:
#
#   /opt/unidocs                     the app (git checkout + venv)
#   /etc/systemd/system/unidocs-server.service
#   /var/lib/unidocs                 the documents (UNIDOCS_DATA_DIR)
#
# Re-running the script updates the checkout and restarts the service.
# Environment variables (optional):
#   UNIDOCS_API_TOKEN   pin the API token (otherwise generated once + printed)
#   UNIDOCS_DATA_DIR    storage folder (default /var/lib/unidocs)
#   UNIDOCS_PORT        TCP port (default 8550)
#   UNIDOCS_DIR         install dir (default /opt/unidocs)

set -euo pipefail

REPO="https://github.com/Lukas-dev-de/UniDocs.git"

INSTALL_DIR="${UNIDOCS_DIR:-/opt/unidocs}"
DATA_DIR="${UNIDOCS_DATA_DIR:-/var/lib/unidocs}"
PORT="${UNIDOCS_PORT:-8550}"
TOKEN_FILE="/etc/unidocs-server.token"

die() { printf 'error: %s\n' "$1" >&2; exit 1; }
info() { printf '  %s\n' "$1"; }

[ "$(id -u)" = 0 ] || die "run as root (packages + systemd unit need it)"

# -- system dependencies -------------------------------------------------
if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y
    apt-get install -y python3 python3-venv python3-pip git curl
else
    die "unsupported distro: need apt (Debian/Ubuntu)"
fi

# -- code ----------------------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    info "updating existing checkout"
    git -C "$INSTALL_DIR" fetch --depth 1 origin main
    git -C "$INSTALL_DIR" reset --hard origin/main
else
    git clone --depth 1 "$REPO" "$INSTALL_DIR"
fi

# -- venv + deps ---------------------------------------------------------
if [ ! -x "$INSTALL_DIR/.venv/bin/python" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR[web]"

# -- API token -----------------------------------------------------------
if [ -n "${UNIDOCS_API_TOKEN:-}" ]; then
    TOKEN="$UNIDOCS_API_TOKEN"
elif [ -f "$TOKEN_FILE" ]; then
    TOKEN="$(cat "$TOKEN_FILE")"
else
    TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    umask 077
    printf '%s\n' "$TOKEN" > "$TOKEN_FILE"
    info "generated a new API token (saved to $TOKEN_FILE)"
fi

mkdir -p "$DATA_DIR"

# -- systemd unit --------------------------------------------------------
cat > /etc/systemd/system/unidocs-server.service <<EOF
[Unit]
Description=UniDocs server (web app + sync API)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/.venv/bin/python tools/serve_web.py --host 0.0.0.0 --port $PORT
Environment=UNIDOCS_API_TOKEN=$TOKEN
Environment=UNIDOCS_DATA_DIR=$DATA_DIR
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now unidocs-server

# -- summary -------------------------------------------------------------
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '\nUniDocs server installed and running.\n'
printf '  Web UI:   http://%s:%s/\n' "${IP:-<server-ip>}" "$PORT"
printf '  Sync URL: http://%s:%s\n' "${IP:-<server-ip>}" "$PORT"
printf '  API token: %s\n' "$TOKEN"
printf '\nDesktop app: Settings -> Cloud sync -> UniDocs server (URL + token).\n'
