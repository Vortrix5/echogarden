-- Phase 7: Grounded Q&A  — conversation_turn extensions + citation table
-- All statements are idempotent.

-- ── Extend conversation_turn with verdict ────────────────
-- (trace_id column added by Phase 3 migration)
-- ALTER TABLE is handled in migrate.py via _safe_add_column.

-- ── Citation table ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_citation (
    citation_id TEXT PRIMARY KEY,
    turn_id     TEXT NOT NULL,
    memory_id   TEXT NOT NULL,
    quote       TEXT,
    span_start  INTEGER,
    span_end    INTEGER,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_chat_citation_turn   ON chat_citation(turn_id);
CREATE INDEX IF NOT EXISTS idx_chat_citation_memory ON chat_citation(memory_id);
