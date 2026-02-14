import logging
import os
from pathlib import Path

from app.core.config import EG_DB_PATH
from app.db.conn import get_conn

logger = logging.getLogger("echogarden.migrate")

_SCHEMA_DIR = Path(__file__).parent
_SCHEMA_FILE = _SCHEMA_DIR / "schema.sql"
_SCHEMA_CAPTURE_FILE = _SCHEMA_DIR / "schema_capture.sql"
_SCHEMA_PHASE3_FILE = _SCHEMA_DIR / "schema_phase3.sql"


def _safe_add_column(conn, table: str, column: str, col_type: str) -> None:
    """Add a column to a table if it doesn't already exist."""
    try:
        existing = [
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info("Added column %s.%s", table, column)
    except Exception as exc:
        logger.debug("Column %s.%s skipped: %s", table, column, exc)


def run_migration() -> None:
    """Create / open the SQLite DB and apply all idempotent schemas."""
    # Ensure the directory for the DB file exists
    os.makedirs(os.path.dirname(EG_DB_PATH), exist_ok=True)

    conn = get_conn()
    try:
        # Core schema (Phase 1 + 2)
        conn.executescript(_SCHEMA_FILE.read_text())
        # Capture subsystem schema (file_state, source, blob, jobs)
        conn.executescript(_SCHEMA_CAPTURE_FILE.read_text())

        # Phase 3: exec_trace table + extensions
        conn.executescript(_SCHEMA_PHASE3_FILE.read_text())

        # Phase 3: add trace_id + timestamp columns to existing tables
        _safe_add_column(conn, "exec_node", "trace_id", "TEXT")
        _safe_add_column(conn, "exec_node", "started_ts", "TEXT")
        _safe_add_column(conn, "exec_node", "finished_ts", "TEXT")
        _safe_add_column(conn, "exec_edge", "trace_id", "TEXT")
        _safe_add_column(conn, "conversation_turn", "trace_id", "TEXT")

        # Indexes on the new trace_id columns
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exec_node_trace ON exec_node(trace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exec_edge_trace ON exec_edge(trace_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conv_turn_trace ON conversation_turn(trace_id)"
        )

        conn.commit()
        logger.info("Phase 3 migration complete")
    finally:
        conn.close()
