#!/usr/bin/env bash
# Deploy the memory server to the Raspberry Pi (bare metal, systemd).
#
# Usage:
#   ./deploy.sh                                      # default host
#   PI_HOST=dennis@192.168.0.203 ./deploy.sh
#   PI_SSH_KEY=~/.ssh/arthur-ledger ./deploy.sh
set -euo pipefail

PI_HOST="${PI_HOST:-dennis@192.168.0.203}"
PI_SSH_KEY="${PI_SSH_KEY:-$HOME/.ssh/arthur-ledger}"
SSH="ssh -i $PI_SSH_KEY"
RSYNC_SSH="ssh -i $PI_SSH_KEY"
REMOTE_DIR="/home/dennis/claude-memory"
SERVICE="claude-memory"

echo "▶ Deploying to $PI_HOST..."

# Ensure remote dir exists
$SSH "$PI_HOST" "mkdir -p $REMOTE_DIR"

# Sync source files
rsync -av --delete \
    -e "$RSYNC_SSH" \
    --exclude='.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.venv' \
    --exclude='data/' \
    . "$PI_HOST:$REMOTE_DIR/"

# Ensure .env exists on Pi
$SSH "$PI_HOST" "
    if [ ! -f $REMOTE_DIR/.env ]; then
        cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env
        echo ''
        echo '⚠️  Created $REMOTE_DIR/.env from .env.example'
        echo '   Set MEMORY_API_KEY before the service will start:'
        echo '   nano $REMOTE_DIR/.env'
        echo ''
        exit 1
    fi
"

# Install/sync dependencies into .venv
$SSH "$PI_HOST" "
    cd $REMOTE_DIR
    ~/.local/bin/uv sync
"

# Install systemd service if not present, then restart
$SSH "$PI_HOST" "
    sudo cp $REMOTE_DIR/claude-memory.service /etc/systemd/system/$SERVICE.service
    sudo systemctl daemon-reload
    sudo systemctl enable $SERVICE
    sudo systemctl restart $SERVICE
"

echo ""
echo "✓ Deployed. Checking health..."
sleep 2
$SSH "$PI_HOST" "curl -sf http://localhost:8765/health && echo ' ← server is up'"

echo ""
echo "If first deploy, connect Tailscale and enable Funnel:"
echo "  $SSH $PI_HOST 'sudo tailscale up'"
echo "  $SSH $PI_HOST 'sudo tailscale funnel 8765'"
echo "  $SSH $PI_HOST 'tailscale status'"
