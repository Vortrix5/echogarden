-- EchoGarden schema v2 — property graph + execution trace
-- All statements are idempotent (IF NOT EXISTS).

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Memory Cards ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memory_card (
    memory_id   TEXT PRIMARY KEY,
    type        TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    source_time TEXT,
    summary     TEXT,
    metadata    JSON
);

-- ── Graph ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS graph_node (
    node_id    TEXT PRIMARY KEY,
    node_type  TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    props      JSON
);

CREATE TABLE IF NOT EXISTS graph_edge (
    edge_id      TEXT PRIMARY KEY,
    from_node_id TEXT NOT NULL REFERENCES graph_node(node_id),
    to_node_id   TEXT NOT NULL REFERENCES graph_node(node_id),
    edge_type    TEXT,
    weight       REAL NOT NULL DEFAULT 1.0,
    valid_from   TEXT,
    valid_to     TEXT,
    provenance   JSON
);

CREATE INDEX IF NOT EXISTS idx_graph_edge_from ON graph_edge(from_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edge_to   ON graph_edge(to_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edge_type ON graph_edge(edge_type);

-- ── Embeddings ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS embedding (
    embedding_id TEXT PRIMARY KEY,
    memory_id    TEXT REFERENCES memory_card(memory_id),
    modality     TEXT NOT NULL DEFAULT 'text',
    vector_ref   TEXT
);

CREATE INDEX IF NOT EXISTS idx_embedding_memory ON embedding(memory_id);

-- ── Citations ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS citation (
    citation_id TEXT PRIMARY KEY,
    memory_id   TEXT REFERENCES memory_card(memory_id),
    span_ref    TEXT,
    quote_hash  TEXT
);

CREATE INDEX IF NOT EXISTS idx_citation_memory ON citation(memory_id);

-- ── Conversation ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversation_turn (
    turn_id        TEXT PRIMARY KEY,
    ts             TEXT NOT NULL DEFAULT (datetime('now')),
    user_text      TEXT,
    assistant_text TEXT
);

-- ── Tool calls & execution DAG ───────────────────────────
CREATE TABLE IF NOT EXISTS tool_call (
    call_id   TEXT PRIMARY KEY,
    tool_name TEXT,
    ts        TEXT NOT NULL DEFAULT (datetime('now')),
    inputs    JSON,
    outputs   JSON,
    status    TEXT
);

CREATE INDEX IF NOT EXISTS idx_tool_call_ts ON tool_call(ts);

CREATE TABLE IF NOT EXISTS exec_node (
    exec_node_id TEXT PRIMARY KEY,
    call_id      TEXT REFERENCES tool_call(call_id),
    state        TEXT,
    attempt      INTEGER NOT NULL DEFAULT 1,
    timeout_ms   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_exec_node_call ON exec_node(call_id);

CREATE TABLE IF NOT EXISTS exec_edge (
    exec_edge_id      TEXT PRIMARY KEY,
    from_exec_node_id TEXT REFERENCES exec_node(exec_node_id),
    to_exec_node_id   TEXT REFERENCES exec_node(exec_node_id),
    condition         TEXT
);

CREATE INDEX IF NOT EXISTS idx_exec_edge_from ON exec_edge(from_exec_node_id);
CREATE INDEX IF NOT EXISTS idx_exec_edge_to   ON exec_edge(to_exec_node_id);

-- ── FTS5 full-text on memory_card ────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS memory_card_fts USING fts5(
    summary,
    content='memory_card',
    content_rowid='rowid'
);
