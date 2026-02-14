"""DB helpers for the capture subsystem: file_state, source, blob, jobs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.conn import get_conn


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ── file_state ────────────────────────────────────────────
def get_file_state(path: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM file_state WHERE path = ?", (path,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_file_state(
    path: str, mtime_ns: int, size_bytes: int, sha256: str
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO file_state (path, mtime_ns, size_bytes, sha256, last_seen_ts)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                   mtime_ns     = excluded.mtime_ns,
                   size_bytes   = excluded.size_bytes,
                   sha256       = excluded.sha256,
                   last_seen_ts = excluded.last_seen_ts""",
            (path, mtime_ns, size_bytes, sha256, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# ── source ────────────────────────────────────────────────
def upsert_source(uri: str, source_type: str = "filesystem") -> str:
    """Insert or return existing source_id for the given URI."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT source_id FROM source WHERE uri = ?", (uri,)
        ).fetchone()
        if row:
            return row["source_id"]
        sid = _new_id()
        conn.execute(
            "INSERT INTO source (source_id, source_type, uri) VALUES (?, ?, ?)",
            (sid, source_type, uri),
        )
        conn.commit()
        return sid
    finally:
        conn.close()


# ── blob ──────────────────────────────────────────────────
def upsert_blob(
    sha256: str,
    path: str,
    mime: str,
    size_bytes: int,
    source_id: str,
) -> str:
    """Insert or return existing blob_id for the given sha256+path."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT blob_id FROM blob WHERE sha256 = ? AND path = ?",
            (sha256, path),
        ).fetchone()
        if row:
            # Update size/mime in case they changed
            conn.execute(
                "UPDATE blob SET mime = ?, size_bytes = ?, source_id = ? WHERE blob_id = ?",
                (mime, size_bytes, source_id, row["blob_id"]),
            )
            conn.commit()
            return row["blob_id"]
        bid = _new_id()
        conn.execute(
            """INSERT INTO blob (blob_id, sha256, path, mime, size_bytes, source_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (bid, sha256, path, mime, size_bytes, source_id),
        )
        conn.commit()
        return bid
    finally:
        conn.close()


# ── jobs ──────────────────────────────────────────────────
def enqueue_job(job_type: str, payload: dict[str, Any]) -> str:
    """Create a new queued job.  Returns job_id."""
    conn = get_conn()
    try:
        # Avoid duplicate queued/running jobs with same payload hash
        payload_str = json.dumps(payload, sort_keys=True)
        existing = conn.execute(
            """SELECT job_id FROM jobs
               WHERE type = ? AND status IN ('queued', 'running')
                 AND payload_json = ?""",
            (job_type, payload_str),
        ).fetchone()
        if existing:
            return existing["job_id"]

        jid = _new_id()
        now = _now_iso()
        conn.execute(
            """INSERT INTO jobs
               (job_id, type, status, created_ts, updated_ts, payload_json)
               VALUES (?, ?, 'queued', ?, ?, ?)""",
            (jid, job_type, now, now, payload_str),
        )
        conn.commit()
        return jid
    finally:
        conn.close()


def claim_job() -> dict[str, Any] | None:
    """Atomically claim the oldest queued job.  Returns row dict or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT * FROM jobs
               WHERE status = 'queued'
               ORDER BY created_ts ASC
               LIMIT 1"""
        ).fetchone()
        if not row:
            return None
        now = _now_iso()
        conn.execute(
            """UPDATE jobs
               SET status = 'running', updated_ts = ?, attempts = attempts + 1
               WHERE job_id = ?""",
            (now, row["job_id"]),
        )
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def complete_job(job_id: str, error: str | None = None) -> None:
    """Mark a job as done or error."""
    status = "error" if error else "done"
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE jobs
               SET status = ?, updated_ts = ?, error_text = ?
               WHERE job_id = ?""",
            (status, _now_iso(), error, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def count_jobs(status: str | None = None) -> int:
    conn = get_conn()
    try:
        if status:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM jobs WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS cnt FROM jobs").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def list_jobs(
    status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    conn = get_conn()
    try:
        if status:
            rows = conn.execute(
                """SELECT * FROM jobs WHERE status = ?
                   ORDER BY created_ts DESC LIMIT ?""",
                (status, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── counters ──────────────────────────────────────────────
def count_file_states() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM file_state").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def count_blobs() -> int:
    conn = get_conn()
    try:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM blob").fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()
