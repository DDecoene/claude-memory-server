"""
Claude Memory MCP Server
Runs on Raspberry Pi, exposed publicly via Tailscale Funnel.
Stores and retrieves personal memories across all Claude Code sessions.
"""
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

# ── Config ────────────────────────────────────────────────────────────────────
DB_PATH = Path(os.environ.get("DB_PATH", "/data/memories.db"))
API_KEY = os.environ.get("MEMORY_API_KEY", "")

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id         TEXT PRIMARY KEY,
                type       TEXT NOT NULL,
                content    TEXT NOT NULL,
                tags       TEXT NOT NULL DEFAULT '[]',
                project    TEXT,
                created_at TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(content, content=memories, content_rowid=rowid);

            -- Keep FTS index in sync with the main table
            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
                INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content)
                    VALUES ('delete', old.rowid, old.content);
            END;
        """)


init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _row(r: sqlite3.Row) -> dict:
    return {
        "id":         r["id"],
        "type":       r["type"],
        "content":    r["content"],
        "tags":       json.loads(r["tags"]),
        "project":    r["project"],
        "created_at": r["created_at"],
    }


def _new_id() -> str:
    return str(uuid.uuid4())[:8]


# ── MCP tools ─────────────────────────────────────────────────────────────────
mcp = FastMCP("claude-memory")


@mcp.tool()
def store_memory(
    content: str,
    memory_type: str,
    tags: list[str] = [],
    project: str | None = None,
) -> dict:
    """
    Persist a memory.

    memory_type options:
      - "profile"  : long-term facts about the user (overwritten by update_profile)
      - "session"  : compressed summary of a work session
      - "decision" : an architectural or technical decision with rationale
      - "fact"     : a discrete fact learned (e.g. "project X uses pattern Y")
    """
    mid = _new_id()
    with db() as c:
        c.execute(
            "INSERT INTO memories VALUES (?,?,?,?,?,?)",
            (mid, memory_type, content, json.dumps(tags), project, datetime.utcnow().isoformat()),
        )
    return {"id": mid, "stored": True}


@mcp.tool()
def search_memories(
    query: str,
    limit: int = 5,
    memory_type: str | None = None,
) -> list[dict]:
    """
    Full-text search across stored memories using SQLite FTS5.
    Returns results ranked by relevance.
    """
    with db() as c:
        if memory_type:
            rows = c.execute(
                """SELECT m.* FROM memories m
                   JOIN memories_fts ON m.rowid = memories_fts.rowid
                   WHERE memories_fts MATCH ? AND m.type = ?
                   ORDER BY rank LIMIT ?""",
                (query, memory_type, limit),
            ).fetchall()
        else:
            rows = c.execute(
                """SELECT m.* FROM memories m
                   JOIN memories_fts ON m.rowid = memories_fts.rowid
                   WHERE memories_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (query, limit),
            ).fetchall()
    return [_row(r) for r in rows]


@mcp.tool()
def get_profile() -> str:
    """Return the current user profile (most recent profile entry)."""
    with db() as c:
        row = c.execute(
            "SELECT content FROM memories WHERE type='profile' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return row["content"] if row else "No profile stored yet. Call update_profile() to create one."


@mcp.tool()
def update_profile(content: str) -> dict:
    """
    Replace the entire user profile with new content.
    The old profile is deleted; only the latest matters.
    """
    with db() as c:
        c.execute("DELETE FROM memories WHERE type='profile'")
    return store_memory(content, "profile")


@mcp.tool()
def get_recent_sessions(n: int = 5) -> list[dict]:
    """Return the n most recent session summaries, newest first."""
    with db() as c:
        rows = c.execute(
            "SELECT * FROM memories WHERE type='session' ORDER BY created_at DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [_row(r) for r in rows]


@mcp.tool()
def list_memories(
    memory_type: str | None = None,
    project: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """List memories with optional filters. Newest first."""
    q, p = "SELECT * FROM memories WHERE 1=1", []
    if memory_type:
        q += " AND type=?"
        p.append(memory_type)
    if project:
        q += " AND project=?"
        p.append(project)
    q += " ORDER BY created_at DESC LIMIT ?"
    p.append(limit)
    with db() as c:
        rows = c.execute(q, p).fetchall()
    return [_row(r) for r in rows]


# ── Auth middleware ───────────────────────────────────────────────────────────

class ApiKeyGuard:
    """
    ASGI middleware: rejects requests without a valid X-API-Key header.
    /health is always allowed (used by Tailscale Funnel health checks).
    If MEMORY_API_KEY env var is not set, auth is skipped entirely.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not API_KEY:
            await self.app(scope, receive, send)
            return

        if scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        if headers.get("x-api-key") != API_KEY:
            await Response("Unauthorized", status_code=401)(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ── HTTP routes ───────────────────────────────────────────────────────────────

async def health(request: Request):
    return JSONResponse({"status": "ok", "service": "claude-memory"})


# ── App assembly ──────────────────────────────────────────────────────────────
# MCP tools are served at /mcp/sse  (SSE transport)
# Configure Claude Code with: "url": "https://YOUR-PI.ts.net/mcp/sse"

app = ApiKeyGuard(
    Starlette(
        routes=[
            Route("/health", health),
            Mount("/mcp", app=mcp.sse_app()),
        ]
    )
)
