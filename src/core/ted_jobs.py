"""ted_jobs: a deliberately thin table — existence, status, timestamps.

The talk's content (brief, script, feedback, audio path) lives only in the
graph checkpoint, the single source of truth; read it with
agents.ted.get_values(job_id).
"""

from __future__ import annotations

from core.db import db

PENDING_APPROVAL = "pending_approval"
AUDIO_READY = "audio_ready"
FAILED = "failed"


def create(job_id: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO ted_jobs (job_id, status) VALUES (?, ?)", (job_id, PENDING_APPROVAL)
        )


def set_status(job_id: str, status: str) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE ted_jobs SET status = ?, updated_at = datetime('now') WHERE job_id = ?",
            (status, job_id),
        )


def get(job_id: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM ted_jobs WHERE job_id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_all() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM ted_jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete(job_id: str) -> bool:
    """Delete the job row and its checkpointed graph thread."""
    from agents.ted.checkpoint import get_saver

    with db() as conn:
        deleted = conn.execute("DELETE FROM ted_jobs WHERE job_id = ?", (job_id,)).rowcount
    get_saver().delete_thread(job_id)
    return deleted > 0
