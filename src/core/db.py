"""Application database: one SQLite file for app-level records (jobs, ...).

Kept separate from the LangGraph checkpoint files on purpose: checkpoints are
the graph's internal state in LangGraph's own format, while this DB holds the
small amount of product bookkeeping the app needs (what exists, its status).
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
APP_DB_PATH = DATA_DIR / "app.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS ted_jobs (
    job_id     TEXT PRIMARY KEY,
    status     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# FastAPI runs sync endpoints in a threadpool: one shared connection guarded by
# a re-entrant lock is enough for this app.
_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def _connection() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(APP_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.executescript(SCHEMA)
    return _conn


@contextmanager
def db():
    """Yield the connection under the lock; commit on success."""
    with _lock:
        conn = _connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
