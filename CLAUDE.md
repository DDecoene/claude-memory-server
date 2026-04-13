# claude-memory

Automatic session memory plugin for Claude Code. Captures tool use, prompts, and observations, then injects relevant context at session start.

**Architecture:** Hook-driven plugin + FastAPI REST server + SQLite FTS5.

## What this is

A Claude Code plugin that automatically records your sessions and injects relevant memories. The server runs in Docker (or locally), stores observations in SQLite with full-text search, and returns the 5 most relevant observations when you start a new session in a project.

**Plugin:** `/plugin` — registers hooks to capture SessionStart, prompts, tool use, and session end.
**Server:** `/server.py` — FastAPI REST endpoints for `/session/start`, `/observe`, `/session/end`.
**Database:** SQLite FTS5 — fast full-text search over observations.

## Running the server

### Docker (recommended)
```bash
docker compose up -d
curl http://localhost:8765/health   # → {"status":"ok","service":"claude-memory"}
```

Data persists in `./data/memories.db`.

### Local development
```bash
DB_PATH=./data/memories.db /opt/homebrew/bin/uv run --with fastapi --with uvicorn python -m uvicorn server:app --reload --port 8765
```

## Environment variables

- `MEMORY_URL` — server URL (default: `http://localhost:8765`). Set on each device.
- `MEMORY_SECRET` — optional Bearer token for auth. Set on both server and client.

**Server-side (docker-compose.yml):**
```yaml
environment:
  - MEMORY_SECRET=${MEMORY_SECRET:-}
  - DB_PATH=/data/memories.db
```

**Client-side (each device):**
```bash
export MEMORY_URL=http://localhost:8765
export MEMORY_SECRET=your-secret-if-enabled
```

## Installing the plugin

The plugin is in `/plugin`. To install in Claude Code:

1. Copy the plugin to your Claude Code plugins directory
2. Ensure `MEMORY_URL` and `MEMORY_SECRET` env vars are set
3. Restart Claude Code

The plugin will then:
- Capture your session start and retrieve relevant context
- Record prompts and tool use (Write, Edit, Bash) to the server
- Store context on session end

## Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/session/start` | POST | Register session, return FTS context |
| `/observe` | POST | Store hook observation (prompt, tool use, etc.) |
| `/session/end` | POST | Mark session as ended |

**POST /session/start:**
```json
{
  "session_id": "ses_abc123",
  "cwd": "/Users/you/Dev/my-project"
}
```
Returns: plain text context (e.g., `[Memory context for ...]\n...`) to inject into system prompt.

**POST /observe:**
```json
{
  "hookType": "prompt_submit",
  "sessionId": "ses_abc123",
  "project": "/Users/you/Dev/my-project",
  "data": {
    "prompt": "rewrite the server as fastapi"
  }
}
```

## Local development

```bash
# Start server
docker compose up -d

# Test with manual hook calls
echo '{"session_id":"test","cwd":"/tmp"}' | MEMORY_URL=http://localhost:8765 node plugin/scripts/session-start.mjs

# Verify data is stored
sqlite3 data/memories.db "SELECT hook_type, content FROM observations LIMIT 5;"

# Stop server
docker compose down
```

## Security

- If `MEMORY_SECRET` is set, all requests require `Authorization: Bearer <SECRET>`.
- `/health` is always allowed (for health checks).
- Port 8765 is bound to `127.0.0.1` only in docker-compose.yml.
- Never commit `.env` files.
