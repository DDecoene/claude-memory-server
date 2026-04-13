# claude-memory Plugin Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite claude-memory-server as a hook-driven Claude Code plugin with a plain FastAPI REST server — no MCP, automatic capture, Docker-first, token-efficient.

**Architecture:** FastAPI server stores selective hook observations in SQLite FTS5. A Claude Code plugin registers hooks that POST to the server. SessionStart injects a small FTS-retrieved context snippet into the system prompt.

**Tech Stack:** Python 3.11, FastAPI, uvicorn, SQLite FTS5, Docker, Node.js (hook scripts, no build step — plain .mjs)

---

### Task 1: Rewrite server.py as pure FastAPI REST server

**Files:**
- Modify: `server.py` (full rewrite)
- Modify: `pyproject.toml` (remove MCP dep, add fastapi)

**Step 1: Update pyproject.toml**

Replace dependencies:
```toml
[project]
name = "claude-memory-server"
version = "0.2.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.30.0",
]
```

**Step 2: Write the new server.py**

```python
"""
claude-memory REST server
Hook-driven memory capture for Claude Code.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.responses import JSONResponse, PlainTextResponse

DB_PATH = Path(os.environ.get("DB_PATH", "/data/memories.db"))
SECRET = os.environ.get("MEMORY_SECRET", "")

DB_PATH.parent.mkdir(parents=True, exist_ok=True)

app = FastAPI()


# ── Database ──────────────────────────────────────────────────────────────────

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                id         TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                hook_type  TEXT NOT NULL,
                project    TEXT,
                content    TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts
                USING fts5(content, content=observations, content_rowid=rowid);

            CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
                INSERT INTO obs_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
                INSERT INTO obs_fts(obs_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
            END;

            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                project    TEXT,
                started_at TEXT NOT NULL,
                ended_at   TEXT
            );
        """)


init_db()


# ── Auth ──────────────────────────────────────────────────────────────────────

def check_auth(request: Request):
    if not SECRET:
        return
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "claude-memory"}


@app.post("/session/start")
async def session_start(request: Request, _=Depends(check_auth)):
    body = await request.json()
    session_id = body.get("session_id") or f"ses_{uuid.uuid4().hex[:8]}"
    project = body.get("cwd") or body.get("project") or ""

    # Register session
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO sessions VALUES (?,?,?,?)",
            (session_id, project, datetime.utcnow().isoformat(), None),
        )

    # FTS search recent observations for this project
    context = ""
    if project:
        with db() as c:
            rows = c.execute(
                """SELECT o.content FROM observations o
                   JOIN obs_fts ON o.rowid = obs_fts.rowid
                   WHERE obs_fts MATCH ? AND o.project = ?
                   ORDER BY rank LIMIT 5""",
                (project.replace("/", " ").strip(), project),
            ).fetchall()
        if not rows:
            # Fall back: just grab the 5 most recent for this project
            with db() as c:
                rows = c.execute(
                    "SELECT content FROM observations WHERE project=? ORDER BY created_at DESC LIMIT 5",
                    (project,),
                ).fetchall()
        if rows:
            snippets = "\n---\n".join(r["content"] for r in rows)
            context = f"[Memory context for {project}]\n{snippets}\n[End memory context]\n\n"

    return PlainTextResponse(context)


@app.post("/observe")
async def observe(request: Request, _=Depends(check_auth)):
    body = await request.json()
    hook_type = body.get("hookType", "unknown")
    session_id = body.get("sessionId", "unknown")
    project = body.get("project") or body.get("cwd") or ""
    data = body.get("data", {})

    # Flatten data to a readable string for FTS
    content_parts = [f"hook:{hook_type}", f"session:{session_id}"]
    if project:
        content_parts.append(f"project:{project}")
    for k, v in data.items():
        if v:
            val = v if isinstance(v, str) else json.dumps(v)
            content_parts.append(f"{k}: {val[:2000]}")  # cap per field

    content = "\n".join(content_parts)

    with db() as c:
        c.execute(
            "INSERT INTO observations VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:8], session_id, hook_type, project or None,
             content, datetime.utcnow().isoformat()),
        )

    return {"stored": True}


@app.post("/session/end")
async def session_end(request: Request, _=Depends(check_auth)):
    body = await request.json()
    session_id = body.get("sessionId", "unknown")

    with db() as c:
        c.execute(
            "UPDATE sessions SET ended_at=? WHERE id=?",
            (datetime.utcnow().isoformat(), session_id),
        )

    return {"ok": True}
```

**Step 3: Verify server starts**

```bash
cd /Users/dennisdecoene/Dev/claude-memory-server
pip install fastapi uvicorn 2>/dev/null || true
DB_PATH=./data/test.db uvicorn server:app --port 8765
```

Expected: `Application startup complete.` with no errors. Ctrl+C to stop.

**Step 4: Commit**

```bash
git add server.py pyproject.toml
git commit -m "feat: rewrite server as pure FastAPI REST (drop MCP)"
```

---

### Task 2: Update Dockerfile and docker-compose.yml

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`

**Step 1: Update Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard]

COPY server.py .

RUN mkdir -p /data

EXPOSE 8765

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8765"]
```

**Step 2: Update docker-compose.yml**

```yaml
services:
  memory:
    build: .
    ports:
      - "127.0.0.1:8765:8765"
    volumes:
      - ./data:/data
    restart: unless-stopped
    environment:
      - MEMORY_SECRET=${MEMORY_SECRET:-}
      - DB_PATH=/data/memories.db
```

Note: volume is now `./data:/data` (local dir) instead of Pi SSD path, works on any machine.

**Step 3: Build and test**

```bash
docker compose build
docker compose up -d
curl http://localhost:8765/health
```

Expected: `{"status":"ok","service":"claude-memory"}`

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: update Docker config for local-first deployment"
```

---

### Task 3: Create plugin structure and metadata

**Files:**
- Create: `plugin/.claude-plugin/plugin.json`
- Create: `plugin/hooks/hooks.json`

**Step 1: Create plugin.json**

```json
{
  "name": "claude-memory",
  "version": "0.2.0",
  "description": "Automatic session memory for Claude Code. Captures tool use and prompts, injects relevant context at session start.",
  "author": {
    "name": "Dennis Decoene"
  },
  "license": "MIT",
  "repository": "https://github.com/dennisdecoene/claude-memory-server"
}
```

**Step 2: Create hooks.json**

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/scripts/session-start.mjs"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/scripts/observe.mjs"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Write|Edit|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/scripts/observe.mjs"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/scripts/observe.mjs"
          }
        ]
      }
    ],
    "SessionEnd": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node ${CLAUDE_PLUGIN_ROOT}/scripts/session-end.mjs"
          }
        ]
      }
    ]
  }
}
```

**Step 3: Commit**

```bash
git add plugin/
git commit -m "feat: add Claude Code plugin metadata and hook registrations"
```

---

### Task 4: Write hook scripts

**Files:**
- Create: `plugin/scripts/session-start.mjs`
- Create: `plugin/scripts/observe.mjs`
- Create: `plugin/scripts/session-end.mjs`

**Step 1: session-start.mjs**

```javascript
#!/usr/bin/env node
const URL = process.env.MEMORY_URL || "http://localhost:8765";
const SECRET = process.env.MEMORY_SECRET || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (SECRET) h["Authorization"] = `Bearer ${SECRET}`;
  return h;
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }

  try {
    const res = await fetch(`${URL}/session/start`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        session_id: data.session_id,
        cwd: data.cwd,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (res.ok) {
      const text = await res.text();
      if (text) process.stdout.write(text);
    }
  } catch {}
}

main();
```

**Step 2: observe.mjs**

```javascript
#!/usr/bin/env node
const URL = process.env.MEMORY_URL || "http://localhost:8765";
const SECRET = process.env.MEMORY_SECRET || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (SECRET) h["Authorization"] = `Bearer ${SECRET}`;
  return h;
}

function truncate(v, max = 4000) {
  if (typeof v === "string") return v.length > max ? v.slice(0, max) + "[…]" : v;
  if (typeof v === "object" && v !== null) {
    const s = JSON.stringify(v);
    return s.length > max ? s.slice(0, max) + "[…]" : v;
  }
  return v;
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }

  // Determine hook type from available fields
  let hookType = "unknown";
  let payload = {};

  if (data.tool_name !== undefined) {
    hookType = "post_tool_use";
    payload = {
      tool_name: data.tool_name,
      tool_input: data.tool_input,
      tool_output: truncate(data.tool_output),
    };
  } else if (data.prompt !== undefined) {
    hookType = "prompt_submit";
    payload = { prompt: truncate(data.prompt) };
  } else {
    hookType = "stop";
    payload = data;
  }

  try {
    await fetch(`${URL}/observe`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({
        hookType,
        sessionId: data.session_id || "unknown",
        project: data.cwd || "",
        timestamp: new Date().toISOString(),
        data: payload,
      }),
      signal: AbortSignal.timeout(3000),
    });
  } catch {}
}

main();
```

**Step 3: session-end.mjs**

```javascript
#!/usr/bin/env node
const URL = process.env.MEMORY_URL || "http://localhost:8765";
const SECRET = process.env.MEMORY_SECRET || "";

function headers() {
  const h = { "Content-Type": "application/json" };
  if (SECRET) h["Authorization"] = `Bearer ${SECRET}`;
  return h;
}

async function main() {
  let input = "";
  for await (const chunk of process.stdin) input += chunk;
  let data;
  try { data = JSON.parse(input); } catch { return; }

  try {
    await fetch(`${URL}/session/end`, {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ sessionId: data.session_id || "unknown" }),
      signal: AbortSignal.timeout(5000),
    });
  } catch {}
}

main();
```

**Step 4: Test scripts manually**

```bash
echo '{"session_id":"test123","cwd":"/tmp"}' | node plugin/scripts/session-start.mjs
echo '{"session_id":"test123","cwd":"/tmp","prompt":"hello world"}' | node plugin/scripts/observe.mjs
echo '{"session_id":"test123"}' | node plugin/scripts/session-end.mjs
```

Expected: no errors, session-start prints empty string (no prior observations), observe and session-end exit silently.

**Step 5: Verify data is stored**

```bash
sqlite3 data/memories.db "SELECT hook_type, content FROM observations LIMIT 5;"
```

Expected: row with `prompt_submit` containing the test prompt.

**Step 6: Commit**

```bash
git add plugin/scripts/
git commit -m "feat: add hook scripts for session-start, observe, session-end"
```

---

### Task 5: Remove obsolete files and update CLAUDE.md

**Files:**
- Delete: `claude-memory.service`
- Delete: `deploy.sh`
- Delete: `requirements.txt`
- Delete: `client-config/` (entire dir)
- Modify: `CLAUDE.md`

**Step 1: Remove Pi-specific files**

```bash
git rm claude-memory.service deploy.sh requirements.txt
git rm -r client-config/
```

**Step 2: Rewrite CLAUDE.md**

Update to reflect the new architecture — Docker-first, plugin-based, no Pi references.

Key sections to cover:
- What this is (plugin + server)
- How to run the server (`docker compose up -d`)
- Env vars (`MEMORY_URL`, `MEMORY_SECRET`)
- How to install the plugin
- Local dev (`uvicorn server:app --reload --port 8765`)

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "chore: remove Pi deployment files, update CLAUDE.md for plugin architecture"
```

---

### Task 6: End-to-end smoke test

**Goal:** Confirm the full hook → server → storage → injection loop works.

**Step 1: Start server**

```bash
docker compose up -d
curl http://localhost:8765/health
```

**Step 2: Simulate SessionStart**

```bash
echo '{"session_id":"e2e_test","cwd":"/Users/dennisdecoene/Dev/claude-memory-server"}' \
  | MEMORY_URL=http://localhost:8765 node plugin/scripts/session-start.mjs
```

Expected: empty output (no prior context).

**Step 3: Simulate some observations**

```bash
echo '{"session_id":"e2e_test","cwd":"/Users/dennisdecoene/Dev/claude-memory-server","prompt":"rewrite the server as pure fastapi"}' \
  | MEMORY_URL=http://localhost:8765 node plugin/scripts/observe.mjs

echo '{"session_id":"e2e_test","cwd":"/Users/dennisdecoene/Dev/claude-memory-server","tool_name":"Write","tool_input":{"file_path":"server.py"},"tool_output":"ok"}' \
  | MEMORY_URL=http://localhost:8765 node plugin/scripts/observe.mjs
```

**Step 4: Simulate new session start for same project**

```bash
echo '{"session_id":"e2e_test2","cwd":"/Users/dennisdecoene/Dev/claude-memory-server"}' \
  | MEMORY_URL=http://localhost:8765 node plugin/scripts/session-start.mjs
```

Expected: output contains `[Memory context for ...]` with the observations from step 3.

**Step 5: Commit**

```bash
git commit --allow-empty -m "test: e2e smoke test passed"
```
