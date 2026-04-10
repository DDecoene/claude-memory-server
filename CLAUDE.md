# claude-memory-server

Personal memory MCP server for Claude Code. Runs on a Raspberry Pi 3B+ with USB SSD,
exposed publicly via Tailscale Funnel so it works with all Claude Code variants
(CLI, desktop, IDE extensions, web).

## What this is

A FastAPI + MCP server that gives Claude Code persistent memory across all sessions,
devices, and repos. Stores memories in SQLite with FTS5 full-text search.

## Architecture

- `server.py` — entire server in one file (FastAPI + FastMCP + SQLite)
- `Dockerfile` + `docker-compose.yml` — containerised deployment
- `deploy.sh` — rsync + restart script for the Pi
- `client-config/` — templates to configure Claude Code on each device

## MCP tools exposed

| Tool | Purpose |
|------|---------|
| `store_memory(content, memory_type, tags?, project?)` | Save a memory |
| `search_memories(query, limit?, memory_type?)` | Full-text search |
| `get_profile()` | Load the user profile |
| `update_profile(content)` | Replace the entire profile |
| `get_recent_sessions(n?)` | Last N session summaries |
| `list_memories(memory_type?, project?, limit?)` | Filtered listing |

memory_type values: `profile` · `session` · `decision` · `fact`

## Deployment (Raspberry Pi)

### One-time Pi setup
```bash
# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up

# Install Docker
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER

# Mount USB SSD
sudo mkdir -p /mnt/ssd/claude-memory
# add to /etc/fstab for auto-mount

Deploy
cp .env.example .env && nano .env   # set MEMORY_API_KEY
PI_HOST=pi@raspberrypi.local ./deploy.sh

Expose publicly via Tailscale Funnel
sudo tailscale funnel 8765
tailscale status   # note your URL: https://your-pi.tail1234.ts.net

Verify
curl https://your-pi.tail1234.ts.net/health   # → {"status":"ok"}

Client setup (each device)
FUNNEL_URL=https://your-pi.tail1234.ts.net ./client-config/setup.sh

Also add to ~/.zshrc:

export MEMORY_API_KEY=your-secret-from-dot-env

Local development
DB_PATH=./data/memories.db uvicorn server:app --reload --port 8765

Security notes
MEMORY_API_KEY must be set in .env on the Pi and in shell on each client device
Port 8765 is bound to 127.0.0.1 only — Tailscale Funnel proxies inbound traffic
Never commit .env
