"""DB helpers for tool_calls, exec_nodes, conversation_turns, memory_cards, and exec_traces."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.conn import get_conn


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


# ── memory_card ───────────────────────────────────────────
def insert_memory_card(
    memory_id: str,
    card_type: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO memory_card (memory_id, type, summary, metadata)
               VALUES (?, ?, ?, ?)""",
            (memory_id, card_type, summary, json.dumps(metadata) if metadata else None),
        )
        # Sync FTS index
        conn.execute(
            """INSERT INTO memory_card_fts (rowid, summary)
               SELECT rowid, summary FROM memory_card WHERE memory_id = ?""",
            (memory_id,),
        )
        conn.commit()
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
        row = conn.execute(
            """SELECT memory_id FROM memory_card
               WHERE metadata LIKE ?
               LIMIT 1""",
            (f'%"blob_id": "{blob_id}"%',),
        ).fetchone()
        if row:
            return row["memory_id"]
        # Also try compact JSON format
        row = conn.execute(
            """SELECT memory_id FROM memory_card
               WHERE metadata LIKE ?
               LIMIT 1""",
            (f'%"blob_id":"{blob_id}"%',),
        ).fetchone()
        return row["memory_id"] if row else None
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
