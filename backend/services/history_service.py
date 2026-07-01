from __future__ import annotations

"""
history_service.py
==================
Historial persistente de ejecuciones usando SQLite.
Registra: usuario, operación, hora inicio/fin, duración, estado, resultado.
"""

import json
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if getattr(sys, "frozen", False):
    # .exe: guardar la DB junto al ejecutable (directorio escribible)
    DB_PATH = Path(sys.executable).parent / "data" / "history.db"
else:
    DB_PATH = Path(__file__).resolve().parents[2] / "data" / "history.db"
_lock = threading.Lock()


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        with _get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS executions (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    username    TEXT    NOT NULL DEFAULT '',
                    command_id  TEXT    NOT NULL,
                    label       TEXT    NOT NULL,
                    category    TEXT    NOT NULL DEFAULT '',
                    started_at  TEXT    NOT NULL,
                    finished_at TEXT,
                    duration_ms INTEGER,
                    status      TEXT    NOT NULL DEFAULT 'running',
                    result      TEXT,
                    error       TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_started ON executions (started_at DESC)
            """)
            conn.commit()


def start_execution(
    username: str,
    command_id: str,
    label: str,
    category: str,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        with _get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO executions
                   (username, command_id, label, category, started_at, status)
                   VALUES (?, ?, ?, ?, ?, 'running')""",
                (username, command_id, label, category, now),
            )
            conn.commit()
            return cur.lastrowid


def finish_execution(
    exec_id: int,
    status: str,
    result: Optional[Any] = None,
    error: Optional[str] = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    result_str = json.dumps(result) if result is not None else None
    with _lock:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT started_at FROM executions WHERE id = ?", (exec_id,)
            ).fetchone()
            duration_ms = None
            if row:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                    finished = datetime.fromisoformat(now)
                    duration_ms = int((finished - started).total_seconds() * 1000)
                except Exception:
                    pass
            conn.execute(
                """UPDATE executions
                   SET finished_at = ?, status = ?, result = ?, error = ?,
                       duration_ms = ?
                   WHERE id = ?""",
                (now, status, result_str, error, duration_ms, exec_id),
            )
            conn.commit()


def get_history(limit: int = 100, offset: int = 0) -> list[dict]:
    with _lock:
        with _get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM executions
                   ORDER BY started_at DESC
                   LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
    return [dict(r) for r in rows]


def get_execution(exec_id: int) -> Optional[dict]:
    with _lock:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM executions WHERE id = ?", (exec_id,)
            ).fetchone()
    return dict(row) if row else None


def get_stats() -> dict:
    with _lock:
        with _get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
            success = conn.execute(
                "SELECT COUNT(*) FROM executions WHERE status = 'success'"
            ).fetchone()[0]
            error = conn.execute(
                "SELECT COUNT(*) FROM executions WHERE status = 'error'"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM executions WHERE status = 'running'"
            ).fetchone()[0]
    return {
        "total": total,
        "success": success,
        "error": error,
        "running": running,
    }


# Initialise on import
init_db()
