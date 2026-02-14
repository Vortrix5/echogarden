import os
from pathlib import Path

from app.core.config import EG_DB_PATH
from app.db.conn import get_conn

_SCHEMA_DIR = Path(__file__).parent
_SCHEMA_FILE = _SCHEMA_DIR / "schema.sql"
_SCHEMA_CAPTURE_FILE = _SCHEMA_DIR / "schema_capture.sql"


def run_migration() -> None:
    """Create / open the SQLite DB and apply all idempotent schemas."""
    # Ensure the directory for the DB file exists
    os.makedirs(os.path.dirname(EG_DB_PATH), exist_ok=True)

    conn = get_conn()
    try:
        # Core schema
        conn.executescript(_SCHEMA_FILE.read_text())
        # Capture subsystem schema (file_state, source, blob, jobs)
        conn.executescript(_SCHEMA_CAPTURE_FILE.read_text())
        conn.commit()
    finally:
        conn.close()
