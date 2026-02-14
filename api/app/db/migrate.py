import os
from pathlib import Path

from app.core.config import EG_DB_PATH
from app.db.conn import get_conn

_SCHEMA_FILE = Path(__file__).parent / "schema.sql"


def run_migration() -> None:
    """Create / open the SQLite DB and apply the idempotent schema."""
    # Ensure the directory for the DB file exists
    os.makedirs(os.path.dirname(EG_DB_PATH), exist_ok=True)

    schema_sql = _SCHEMA_FILE.read_text()
    conn = get_conn()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
