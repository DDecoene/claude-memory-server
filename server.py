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
