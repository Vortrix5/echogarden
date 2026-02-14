-- EchoGarden Phase 3 — Execution trace + idempotency
-- All statements are idempotent (IF NOT EXISTS).

-- ── Execution Trace (root of a pipeline run) ─────────────
CREATE TABLE IF NOT EXISTS exec_trace (
    trace_id       TEXT PRIMARY KEY,
    started_ts     TEXT NOT NULL DEFAULT (datetime('now')),
    finished_ts    TEXT,
    status         TEXT NOT NULL DEFAULT 'running',
    root_call_id   TEXT,
    metadata_json  TEXT
);

CREATE INDEX IF NOT EXISTS idx_exec_trace_status ON exec_trace(status);

-- ── Extend exec_node with trace_id + timestamps ─────────
-- Phase 1 already created exec_node; add columns if missing.
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we
-- use a helper approach: attempt the ALTER and ignore errors.
-- These are handled in migrate.py programmatically.

-- ── Extend exec_edge with trace_id ──────────────────────
-- Same approach — handled in migrate.py.

-- ── Conversation turn: add trace_id column ───────────────
-- Handled in migrate.py.

-- ── Idempotency index: prevent duplicate memory cards for
-- the same blob_id within the same trace.
-- We rely on a lookup in metadata->blob_id before inserting.
-- No schema change needed; logic is in repo.py.
