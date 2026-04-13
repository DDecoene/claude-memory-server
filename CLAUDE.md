# claude-memory-server

Personal memory MCP server for Claude Code. Runs on a Raspberry Pi 3B+ with USB SSD,
exposed publicly via Tailscale Funnel so it works with all Claude Code variants
(CLI, desktop, IDE extensions, web).

## What this is

A FastAPI + MCP server that gives Claude Code persistent memory across all sessions,
devices, and repos. Stores memories in SQLite with FTS5 full-text search.

## Architecture

- `server.py` — entire server in one file (FastAPI + FastMCP + SQLite)
- `pyproject.toml` — dependencies for `uv`
- `claude-memory.service` — systemd unit file (copied to Pi by deploy.sh)
- `deploy.sh` — rsync + systemd restart script for the Pi
- `client-config/` — templates to configure Claude Code on each device

> **Deployment target:** bare metal on Pi (not Docker). Pi 3B+ only has 1GB RAM; Docker overhead isn't worth it for a single Python process + SQLite.
> **Python tooling:** `uv` (installed at `~/.local/bin/uv`) — manages virtualenv and dependencies, no system pip needed.

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

## Pi network details

- **Local IP:** `192.168.0.203` (confirmed via nmap, MAC: `B8:27:EB:F5:48:C8`)
- **mDNS hostname:** `resonantreal.local` (may not always resolve)
- **SSH:** `ssh -i ~/.ssh/arthur-ledger dennis@192.168.0.203`
- **Public URL:** `https://arthur-ledger.tail4d0dfe.ts.net` (Tailscale Funnel)

## Deployment (Raspberry Pi)

### One-time Pi setup (already done)
- `uv` installed at `~/.local/bin/uv`
- Tailscale installed (needs `sudo tailscale up` to authenticate)

### Deploy
```bash
# First deploy: create .env on the Pi
ssh -i ~/.ssh/arthur-ledger dennis@192.168.0.203 "cp ~/claude-memory/.env.example ~/claude-memory/.env && nano ~/claude-memory/.env"

# Deploy (subsequent)
./deploy.sh
```

### Expose via Tailscale Funnel
```bash
ssh -i ~/.ssh/arthur-ledger dennis@192.168.0.203
sudo tailscale up          # authenticate (one-time)
sudo tailscale funnel 8765
tailscale status           # note your URL: https://your-pi.tail1234.ts.net
```

### Verify
```bash
curl https://your-pi.tail1234.ts.net/health   # → {"status":"ok"}
```

### Client setup (each device)
```bash
FUNNEL_URL=https://your-pi.tail1234.ts.net ./client-config/setup.sh
```

Also add to `~/.zshrc`:
```bash
export MEMORY_API_KEY=your-secret-from-dot-env
```

### Local development
```bash
DB_PATH=./data/memories.db uv run uvicorn server:app --reload --port 8765
```

### Security notes
- `MEMORY_API_KEY` must be set in `.env` on the Pi and in shell on each client device
- Port 8765 is bound to `127.0.0.1` only — Tailscale Funnel proxies inbound traffic
- Never commit `.env`
