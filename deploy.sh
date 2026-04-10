#!/usr/bin/env bash
# Deploy the memory server to the Raspberry Pi.
# Prerequisites on the Pi: Docker, docker compose, USB SSD mounted at /mnt/ssd
#
# Usage:
#   PI_HOST=pi@raspberrypi.local ./deploy.sh
#   PI_HOST=pi@100.x.x.x ./deploy.sh     # via Tailscale IP
set -euo pipefail

PI_HOST="${PI_HOST:-pi@raspberrypi.local}"
REMOTE_DIR="/opt/claude-memory"

echo "▶ Deploying to $PI_HOST..."

# Ensure the SSD mount point and data dir exist on the Pi
ssh "$PI_HOST" "sudo mkdir -p /mnt/ssd/claude-memory && sudo chown \$USER /mnt/ssd/claude-memory"

# Sync source files (excluding local .env — never copy secrets over rsync blindly)
rsync -av --delete \
    --exclude='.env' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    . "$PI_HOST:$REMOTE_DIR/"

# If .env doesn't exist on the Pi yet, warn and create from example
ssh "$PI_HOST" "
    if [ ! -f $REMOTE_DIR/.env ]; then
        cp $REMOTE_DIR/.env.example $REMOTE_DIR/.env
        echo ''
        echo '⚠️  Created $REMOTE_DIR/.env from .env.example'
        echo '   Edit it now and set MEMORY_API_KEY before starting:'
        echo '   ssh $PI_HOST nano $REMOTE_DIR/.env'
        echo ''
        exit 1
    fi
"

# Build and restart
ssh "$PI_HOST" "cd $REMOTE_DIR && docker compose up -d --build"

echo ""
echo "✓ Deployed. Checking health..."
sleep 3
ssh "$PI_HOST" "curl -sf http://localhost:8765/health && echo ' ← server is up'"

echo ""
echo "Next: ensure Tailscale Funnel is running on the Pi:"
echo "  ssh $PI_HOST 'sudo tailscale funnel 8765'"
echo "  ssh $PI_HOST 'tailscale status'   # note your public URL"
