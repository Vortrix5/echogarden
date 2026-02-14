"""DB helpers for tool_calls, exec_nodes, conversation_turns, and memory_cards."""

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
