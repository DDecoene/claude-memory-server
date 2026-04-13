# claude-memory-server: Plugin Design

**Date:** 2026-04-13  
**Status:** Approved

## Goal

Rewrite claude-memory-server as a Claude Code plugin that auto-captures session context
via hooks — no MCP, no manual tool calls. Users bring their own server (Docker locally or
any remote host) and point the plugin at it with one env var.

## What We're Dropping

- MCP interface (SSE transport, all MCP tools)
- Pi deployment focus
- Reliance on Claude explicitly calling `store_memory` etc.

## Architecture

Single Python file (`server.py`) — FastAPI only, SQLite + FTS5. Runs in Docker.
Plugin lives in `plugin/` and registers hooks into Claude Code automatically on install.

```
claude-memory-server/
  server.py                          # FastAPI server, all logic
  Dockerfile
  docker-compose.yml
  plugin/
    .claude-plugin/plugin.json       # Plugin metadata
    hooks/hooks.json                 # Hook registrations
    scripts/                         # Thin Node.js hook scripts
      session-start.mjs
      observe.mjs                    # Shared observe poster
      session-end.mjs
```

## Server: REST Endpoints

| Method | Path | Triggered by | Purpose |
|--------|------|-------------|---------|
| `POST` | `/session/start` | SessionStart | FTS search recent context, return as string injected into system prompt |
| `POST` | `/observe` | UserPromptSubmit, PostToolUse, Stop | Store raw observation |
| `POST` | `/session/end` | SessionEnd | Store lightweight session summary, mark closed |
| `GET`  | `/health` | — | Liveness check |

Auth: `Authorization: Bearer <MEMORY_SECRET>`. If `MEMORY_SECRET` not set, auth skipped.

### `/session/start` response

Returns a plain text string (written to stdout by the hook script) that Claude Code
injects as a system-prompt prefix. Content: FTS snippet of the 3-5 most relevant recent
observations for the current project.

### `/observe` payload

```json
{
  "hookType": "post_tool_use | prompt_submit | stop",
  "sessionId": "...",
  "project": "/path/to/repo",
  "timestamp": "ISO8601",
  "data": { ... }
}
```

## Hook Filtering (Token Economy)

Only these events are sent to `/observe`:

| Hook | Condition |
|------|-----------|
| `UserPromptSubmit` | Always |
| `PostToolUse` | Tool name is `Write` or `Edit` only |
| `PostToolUse` | Tool name is `Bash` (stored as-is, no filtering yet) |
| `Stop` | Always |
| `PreToolUse` | Never captured |
| `PostToolUse` for Read/Glob/Grep | Never captured |

Future: LLM compression, smarter retrieval (RAG), decay/forgetting.

## Plugin Registration

`hooks/hooks.json` registers:
- `SessionStart` → `session-start.mjs`
- `UserPromptSubmit` → `observe.mjs`
- `PostToolUse` (matcher: `Write|Edit|Bash`) → `observe.mjs`
- `Stop` → `observe.mjs`
- `SessionEnd` → `session-end.mjs`

## Environment Variables

**Server (`docker-compose.yml` / `.env`):**
- `MEMORY_SECRET` — bearer token for auth
- `DB_PATH` — SQLite path (default `/data/memories.db`)

**Client (shell profile):**
- `MEMORY_URL` — server URL (default `http://localhost:8765`)
- `MEMORY_SECRET` — must match server

## User Setup

```bash
# 1. Start server
docker compose up -d

# 2. Set env vars (add to ~/.zshrc)
export MEMORY_URL=http://localhost:8765   # or https://your-remote-server
export MEMORY_SECRET=your-secret

# 3. Install plugin
/plugin install your-github/claude-memory-server
```

## Design Decisions

- **No LLM on server** — keeps it cheap to run; FTS is good enough for now
- **Raw storage** — observations stored as-is; smarter compression is future work
- **Bearer token auth** — matches agentmemory convention, easier for users already familiar
- **Docker-first** — keeps user's machine clean; works on Mac/Linux/VPS
- **Plugin distribution** — hooks auto-register, zero manual settings.json editing
