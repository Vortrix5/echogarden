import sqlite3

from app.core.config import EG_DB_PATH


def get_conn() -> sqlite3.Connection:
    """Return a new SQLite connection with Row factory and FK enforcement."""
    conn = sqlite3.connect(EG_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
