-- Phase 8: conversation threads, conversation_turn_v2, search_query
CREATE TABLE IF NOT EXISTS conversation (
    conversation_id  TEXT PRIMARY KEY,
    title            TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_turn_v2 (
    turn_id          TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversation(conversation_id),
    user_text        TEXT,
    assistant_text   TEXT,
    verdict          TEXT,
    citations_json   TEXT,
    evidence_json    TEXT,
    trace_id         TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ctv2_conv ON conversation_turn_v2(conversation_id);

CREATE TABLE IF NOT EXISTS search_query (
    search_id        TEXT PRIMARY KEY,
    query_text       TEXT NOT NULL,
    filters_json     TEXT,
    result_count     INTEGER DEFAULT 0,
    trace_id         TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sq_created ON search_query(created_at);
