-- EchoGarden Capture schema — file watcher + job queue
-- All statements are idempotent (IF NOT EXISTS).

-- ── Sources ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source (
    source_id   TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,          -- 'filesystem', 'api', etc.
    uri         TEXT NOT NULL UNIQUE,   -- absolute host path or URL
    created_ts  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Blobs ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS blob (
    blob_id     TEXT PRIMARY KEY,
    sha256      TEXT NOT NULL,
    path        TEXT NOT NULL,           -- path inside container
    mime        TEXT,
    size_bytes  INTEGER NOT NULL,
    source_id   TEXT REFERENCES source(source_id),
    created_ts  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_blob_sha256    ON blob(sha256);
CREATE INDEX IF NOT EXISTS idx_blob_source    ON blob(source_id);

-- ── File State (dedup tracker) ───────────────────────────
CREATE TABLE IF NOT EXISTS file_state (
    path         TEXT PRIMARY KEY,
    mtime_ns     INTEGER NOT NULL,
    size_bytes   INTEGER NOT NULL,
    sha256       TEXT NOT NULL,
    last_seen_ts TEXT NOT NULL
);

-- ── Jobs (async work queue) ──────────────────────────────
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    type         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued',
    created_ts   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_ts   TEXT NOT NULL DEFAULT (datetime('now')),
    attempts     INTEGER NOT NULL DEFAULT 0,
    next_run_ts  TEXT,
    payload_json TEXT NOT NULL,
    error_text   TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status      ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type        ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_next_run    ON jobs(next_run_ts);
