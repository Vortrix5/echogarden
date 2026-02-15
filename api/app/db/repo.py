"""DB helpers for tool_calls, exec_nodes, conversation_turns, memory_cards, and exec_traces."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.conn import get_conn

logger = logging.getLogger("echogarden.db.repo")

# ── schema introspection ──────────────────────────────────

def _table_columns(conn, table: str) -> list[str]:
    """Return column names for a table."""
    try:
        rows = conn.execute(f"PRAGMA table_info([{table}])").fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


def _table_exists(conn, table: str) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row[0] > 0


def get_memory_card_table() -> str:
    """Detect the actual memory card table name.
    Prefer MEMORY_CARD if it exists, otherwise memory_card.
    """
    conn = get_conn()
    try:
        if _table_exists(conn, "MEMORY_CARD"):
            return "MEMORY_CARD"
        return "memory_card"
    finally:
        conn.close()


def ensure_memory_card_columns() -> None:
    """Introspect the memory_card table and add any missing Phase 6 columns.
    
    Required columns:
      memory_id (TEXT PK) | type | created_at | source_time | summary
      content_text | metadata_json
    """
    conn = get_conn()
    try:
        table = get_memory_card_table()
        existing = _table_columns(conn, table)
        if not existing:
            logger.warning("Memory card table '%s' not found; migration will create it", table)
            return

        needed = {
            "content_text": "TEXT",
            "metadata_json": "TEXT",
            "source_time": "TEXT",
            "type": "TEXT",
            "created_at": "TEXT",
            "summary": "TEXT",
        }
        for col, col_type in needed.items():
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE [{table}] ADD COLUMN {col} {col_type}")
                    logger.info("Added column %s.%s (%s)", table, col, col_type)
                except Exception as exc:
                    logger.debug("Column %s.%s skipped: %s", table, col, exc)

        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── tool_call ─────────────────────────────────────────────
def insert_tool_call(
    call_id: str,
    tool_name: str,
    inputs: dict[str, Any],
    status: str = "running",
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO tool_call (call_id, tool_name, ts, inputs, outputs, status)
               VALUES (?, ?, ?, ?, NULL, ?)""",
            (call_id, tool_name, _now_iso(), json.dumps(inputs), status),
        )
        conn.commit()
    finally:
        conn.close()


def update_tool_call(
    call_id: str,
    outputs: dict[str, Any] | None,
    status: str,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE tool_call SET outputs = ?, status = ? WHERE call_id = ?""",
            (json.dumps(outputs) if outputs is not None else None, status, call_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── exec_node ─────────────────────────────────────────────
def insert_exec_node(
    exec_node_id: str,
    call_id: str,
    state: str = "running",
    attempt: int = 1,
    timeout_ms: int = 8000,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO exec_node (exec_node_id, call_id, state, attempt, timeout_ms)
               VALUES (?, ?, ?, ?, ?)""",
            (exec_node_id, call_id, state, attempt, timeout_ms),
        )
        conn.commit()
    finally:
        conn.close()


def update_exec_node(exec_node_id: str, state: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE exec_node SET state = ? WHERE exec_node_id = ?""",
            (state, exec_node_id),
        )
        conn.commit()
    finally:
        conn.close()


# ── exec_edge ─────────────────────────────────────────────
def insert_exec_edge(
    from_exec_node_id: str,
    to_exec_node_id: str,
    condition: str | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO exec_edge (exec_edge_id, from_exec_node_id, to_exec_node_id, condition)
               VALUES (?, ?, ?, ?)""",
            (uuid.uuid4().hex, from_exec_node_id, to_exec_node_id, condition),
        )
        conn.commit()
    finally:
        conn.close()


# ── conversation_turn ─────────────────────────────────────
def insert_conversation_turn(
    turn_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO conversation_turn (turn_id, ts, user_text, assistant_text)
               VALUES (?, ?, ?, ?)""",
            (turn_id, _now_iso(), user_text, assistant_text),
        )
        conn.commit()
    finally:
        conn.close()


# ── content caps ──────────────────────────────────────────
_MAX_SUMMARY_CHARS = 400
_MAX_CONTENT_TEXT_CHARS = 200_000

# ── memory_card ───────────────────────────────────────────
def insert_memory_card(
    memory_id: str,
    card_type: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    content_text: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> None:
    """Insert a memory card. Phase 6: stores content_text and metadata_json.

    Enforces:
      - summary max 400 chars (hard truncate)
      - content_text max 200k chars (hard truncate)
      - summary != content_text
    Legacy callers that only pass metadata still work (backwards compatible).
    """
    # Enforce summary cap
    if summary and len(summary) > _MAX_SUMMARY_CHARS:
        summary = summary[:_MAX_SUMMARY_CHARS - 3].rstrip() + "..."

    # Enforce content_text cap
    if content_text and len(content_text) > _MAX_CONTENT_TEXT_CHARS:
        content_text = content_text[:_MAX_CONTENT_TEXT_CHARS]

    # Prevent summary == content_text
    if summary and content_text and summary == content_text[:len(summary)]:
        cut = content_text[:_MAX_SUMMARY_CHARS]
        for sep in (". ", ".\n"):
            idx = cut.rfind(sep)
            if idx > 30:
                summary = cut[:idx + 1].strip()
                break

    # Merge legacy metadata into metadata_json if metadata_json not provided
    if metadata_json is None and metadata is not None:
        metadata_json = metadata

    meta_str = json.dumps(metadata_json) if metadata_json else (json.dumps(metadata) if metadata else None)

    conn = get_conn()
    try:
        table = get_memory_card_table()
        cols = _table_columns(conn, table)

        # Build dynamic INSERT based on available columns
        col_names = ["memory_id", "type", "summary"]
        values: list = [memory_id, card_type, summary]

        if "content_text" in cols and content_text is not None:
            col_names.append("content_text")
            values.append(content_text)

        if "metadata_json" in cols and meta_str is not None:
            col_names.append("metadata_json")
            values.append(meta_str)
        elif "metadata" in cols and meta_str is not None:
            col_names.append("metadata")
            values.append(meta_str)

        placeholders = ", ".join("?" for _ in col_names)
        sql = f"INSERT INTO [{table}] ({', '.join(col_names)}) VALUES ({placeholders})"
        conn.execute(sql, values)

        # Sync FTS index (best-effort)
        try:
            conn.execute(
                f"""INSERT INTO memory_card_fts (rowid, summary)
                   SELECT rowid, summary FROM [{table}] WHERE memory_id = ?""",
                (memory_id,),
            )
        except Exception:
            pass  # FTS table may not exist

        conn.commit()
    finally:
        conn.close()


# ── embedding ─────────────────────────────────────────────
def insert_embedding(
    memory_id: str,
    modality: str = "text",
    vector_ref: str = "",
) -> str:
    """Insert an EMBEDDING row linking a memory card to a Qdrant vector."""
    embedding_id = uuid.uuid4().hex
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO embedding (embedding_id, memory_id, modality, vector_ref)
               VALUES (?, ?, ?, ?)""",
            (embedding_id, memory_id, modality, vector_ref),
        )
        conn.commit()
        return embedding_id
    finally:
        conn.close()


def get_embeddings_for_memory(memory_id: str) -> list[dict[str, Any]]:
    """Return all EMBEDDING rows for a memory card."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM embedding WHERE memory_id = ?", (memory_id,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fts_search_memory_cards(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Full-text search over memory_card.summary via FTS5."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT mc.memory_id, mc.summary, mc.metadata,
                      rank AS score
               FROM memory_card_fts
               JOIN memory_card mc ON mc.rowid = memory_card_fts.rowid
               WHERE memory_card_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (query, limit),
        ).fetchall()
        results = []
        for r in rows:
            results.append({
                "memory_id": r["memory_id"],
                "summary": r["summary"],
                "score": r["score"],
            })
        return results
    except Exception:
        # FTS may fail on empty DB — return empty
        return []
    finally:
        conn.close()


# ── exec_trace ────────────────────────────────────────────
def insert_exec_trace(
    trace_id: str,
    metadata: dict[str, Any] | None = None,
    status: str = "running",
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO exec_trace (trace_id, started_ts, status, metadata_json)
               VALUES (?, ?, ?, ?)""",
            (trace_id, _now_iso(), status, json.dumps(metadata) if metadata else None),
        )
        conn.commit()
    finally:
        conn.close()


def finish_exec_trace(trace_id: str, status: str) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """UPDATE exec_trace SET finished_ts = ?, status = ? WHERE trace_id = ?""",
            (_now_iso(), status, trace_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_exec_trace(trace_id: str) -> dict[str, Any] | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM exec_trace WHERE trace_id = ?", (trace_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_exec_nodes_for_trace(trace_id: str) -> list[dict[str, Any]]:
    """Return all exec_nodes associated with a trace_id."""
    conn = get_conn()
    try:
        # Try trace_id column first; fall back to joining via tool_call metadata
        rows = conn.execute(
            """SELECT en.*, tc.tool_name, tc.ts as call_ts, tc.status as call_status
               FROM exec_node en
               LEFT JOIN tool_call tc ON en.call_id = tc.call_id
               WHERE en.trace_id = ?
               ORDER BY en.started_ts""",
            (trace_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_exec_edges_for_trace(trace_id: str) -> list[dict[str, Any]]:
    """Return all exec_edges associated with a trace_id."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT * FROM exec_edge WHERE trace_id = ?""",
            (trace_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_tool_calls_for_trace(trace_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Return tool_call rows linked to the given trace (via exec_node.trace_id)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT tc.* FROM tool_call tc
               INNER JOIN exec_node en ON tc.call_id = en.call_id
               WHERE en.trace_id = ?
               ORDER BY tc.ts
               LIMIT ?""",
            (trace_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def get_recent_tool_calls(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent tool_call rows."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM tool_call ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── exec_node extensions ──────────────────────────────────
def update_exec_node_trace(exec_node_id: str, trace_id: str) -> None:
    """Set the trace_id on an exec_node (Phase 3 column)."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE exec_node SET trace_id = ? WHERE exec_node_id = ?",
            (trace_id, exec_node_id),
        )
        conn.commit()
    except Exception:
        pass  # column may not exist in older schemas
    finally:
        conn.close()


def get_latest_exec_node_for_call(tool_name: str, trace_id: str) -> dict[str, Any] | None:
    """Find the most recently inserted exec_node for a tool_name within a trace.

    Since BasePassiveAgent persists the exec_node, we look it up via tool_call
    joined to exec_node where tool_call.inputs contains the trace_id.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            """SELECT en.exec_node_id, en.call_id
               FROM exec_node en
               JOIN tool_call tc ON en.call_id = tc.call_id
               WHERE tc.tool_name = ?
                 AND tc.inputs LIKE ?
               ORDER BY tc.ts DESC
               LIMIT 1""",
            (tool_name, f'%{trace_id}%'),
        ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()


# ── idempotency helpers ───────────────────────────────────
def find_memory_card_by_blob(blob_id: str) -> str | None:
    """Return existing memory_id if a card already exists for this blob_id."""
    conn = get_conn()
    try:
        cols = _table_columns(conn, "memory_card")
        # Search both metadata and metadata_json columns
        search_cols = []
        if "metadata_json" in cols:
            search_cols.append("metadata_json")
        if "metadata" in cols:
            search_cols.append("metadata")
        if not search_cols:
            return None

        for col in search_cols:
            for pattern in (f'%"blob_id": "{blob_id}"%', f'%"blob_id":"{blob_id}"%'):
                row = conn.execute(
                    f"SELECT memory_id FROM memory_card WHERE {col} LIKE ? LIMIT 1",
                    (pattern,),
                ).fetchone()
                if row:
                    return row["memory_id"]
        return None
    except Exception:
        return None
    finally:
        conn.close()


# ── conversation_turn extension ───────────────────────────
def insert_conversation_turn(
    turn_id: str,
    user_text: str,
    assistant_text: str,
    trace_id: str | None = None,
) -> None:
    conn = get_conn()
    try:
        # Check if trace_id column exists
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversation_turn)").fetchall()]
        if "trace_id" in cols:
            conn.execute(
                """INSERT INTO conversation_turn (turn_id, ts, user_text, assistant_text, trace_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (turn_id, _now_iso(), user_text, assistant_text, trace_id),
            )
        else:
            conn.execute(
                """INSERT INTO conversation_turn (turn_id, ts, user_text, assistant_text)
                   VALUES (?, ?, ?, ?)""",
                (turn_id, _now_iso(), user_text, assistant_text),
            )
        conn.commit()
    finally:
        conn.close()
