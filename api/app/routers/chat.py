"""Router: Chat — Phase 7 grounded Q&A loop with conversation archive."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.db.conn import get_conn
from app.orchestrator.models import StepResult
from app.orchestrator.orchestrator import Orchestrator

router = APIRouter(tags=["chat"])
_orch = Orchestrator()


# ── Request / Response models ─────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="User question")
    conversation_id: str | None = Field(None, description="Existing conversation ID to continue")
    top_k: int = Field(default=3, ge=1, le=50)
    use_graph: bool = True
    hops: int = Field(default=1, ge=0, le=3)


class CitationOut(BaseModel):
    memory_id: str = ""
    quote: str = ""
    source_type: str = ""
    created_at: str = ""
    title: str = ""
    file_path: str = ""
    url: str = ""
    blob_id: str = ""
    open_url: str = ""


class EvidenceOut(BaseModel):
    memory_id: str = ""
    summary: str = ""
    snippet: str = ""
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    title: str = ""
    source_type: str = ""
    file_path: str = ""
    open_url: str = ""


class ChatResponse(BaseModel):
    trace_id: str
    conversation_id: str = ""
    answer: str
    verdict: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"


# ── Helpers ───────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hydrate_citation(c: dict) -> dict:
    """Enrich a citation dict with human-readable source metadata."""
    mid = c.get("memory_id", "")
    if not mid:
        return c

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT summary, type, created_at, metadata, metadata_json FROM memory_card WHERE memory_id = ?",
            (mid,),
        ).fetchone()
        if not row:
            return c

        meta: dict = {}
        for key in ("metadata_json", "metadata"):
            val = row[key] if key in row.keys() else None
            if val and isinstance(val, str):
                try:
                    meta = json.loads(val)
                    break
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(val, dict):
                meta = val
                break

        title = (row["summary"] or "")[:80] or mid[:16]
        file_path = meta.get("file_path", "")
        url = meta.get("url", "")
        blob_id = meta.get("blob_id", "")
        open_url = f"/api/cards/{mid}/open" if (blob_id or file_path) else ""

        return {
            **c,
            "title": title,
            "source_type": c.get("source_type") or meta.get("source_type", row["type"] or ""),
            "created_at": c.get("created_at") or row["created_at"] or "",
            "file_path": file_path,
            "url": url,
            "blob_id": blob_id,
            "open_url": open_url,
        }
    finally:
        conn.close()


def _hydrate_evidence(ev: dict) -> dict:
    """Enrich an evidence dict with source metadata."""
    mid = ev.get("memory_id", "")
    if not mid:
        return ev

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT summary, metadata, metadata_json FROM memory_card WHERE memory_id = ?",
            (mid,),
        ).fetchone()
        if not row:
            return ev

        meta: dict = {}
        for key in ("metadata_json", "metadata"):
            val = row[key] if key in row.keys() else None
            if val and isinstance(val, str):
                try:
                    meta = json.loads(val)
                    break
                except (json.JSONDecodeError, TypeError):
                    pass
            elif isinstance(val, dict):
                meta = val
                break

        title = (row["summary"] or "")[:80] or mid[:16]
        file_path = meta.get("file_path", "")
        blob_id = meta.get("blob_id", "")
        open_url = f"/api/cards/{mid}/open" if (blob_id or file_path) else ""

        return {
            **ev,
            "title": title,
            "file_path": file_path,
            "open_url": open_url,
            "source_type": ev.get("source_type") or meta.get("source_type", ""),
        }
    finally:
        conn.close()


def _humanize_answer(answer: str, citations: list[dict], evidence: list[dict]) -> str:
    """Replace raw [memory_id] references in the answer with human-readable [filename] labels."""
    import re as _re
    # Build a map: memory_id -> display label
    label_map: dict[str, str] = {}
    for item in citations + evidence:
        mid = item.get("memory_id", "")
        if not mid or mid in label_map:
            continue
        fp = item.get("file_path", "")
        title = item.get("title", "")
        if fp:
            import os as _os
            label_map[mid] = _os.path.basename(fp)
        elif title:
            label_map[mid] = title[:50]
        else:
            label_map[mid] = mid[:12]

    # Replace [memory_id] and - [memory_id] patterns
    def _replace(m: _re.Match) -> str:
        mid = m.group(1)
        label = label_map.get(mid, mid[:12])
        return m.group(0).replace(mid, label)

    # Match [hex_id] patterns (32-char hex memory IDs)
    answer = _re.sub(r'\[([a-f0-9]{16,64})\]', _replace, answer)
    return answer


def _get_or_create_conversation(conversation_id: str | None, first_message: str) -> str:
    """Return existing conversation_id or create a new one."""
    conn = get_conn()
    try:
        if conversation_id:
            row = conn.execute(
                "SELECT conversation_id FROM conversation WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE conversation SET updated_at = ? WHERE conversation_id = ?",
                    (_now_iso(), conversation_id),
                )
                conn.commit()
                return conversation_id

        # Create new conversation
        cid = uuid.uuid4().hex
        title = first_message[:60].strip() or "New conversation"
        now = _now_iso()
        conn.execute(
            "INSERT INTO conversation (conversation_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )
        conn.commit()
        return cid
    finally:
        conn.close()


def _save_turn(conversation_id: str, user_text: str, assistant_text: str, trace_id: str, verdict: str) -> None:
    """Insert a conversation turn linked to its conversation."""
    conn = get_conn()
    try:
        turn_id = uuid.uuid4().hex
        conn.execute(
            """INSERT INTO conversation_turn_v2
               (turn_id, conversation_id, user_text, assistant_text, verdict, trace_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (turn_id, conversation_id, user_text, assistant_text, verdict, trace_id, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


# ── Endpoint ─────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    """Grounded Q&A: retrieval → weaver → verifier → answer + citations + trace.

    Supports conversation threading via optional conversation_id.
    """
    result = await _orch.chat(
        req.message,
        top_k=req.top_k,
        use_graph=req.use_graph,
        hops=req.hops,
    )

    # Hydrate citations & evidence with human-readable source info
    hydrated_citations = [_hydrate_citation(c) for c in result.citations]
    hydrated_evidence = [_hydrate_evidence(e) for e in result.evidence]

    # Post-process the answer: replace raw [memory_id] refs with [filename]
    answer_text = _humanize_answer(result.answer, hydrated_citations, hydrated_evidence)

    # Persist conversation
    conv_id = _get_or_create_conversation(req.conversation_id, req.message)
    _save_turn(conv_id, req.message, answer_text, result.trace_id, result.verdict)

    return ChatResponse(
        trace_id=result.trace_id,
        conversation_id=conv_id,
        answer=answer_text,
        verdict=result.verdict,
        citations=[CitationOut(**c) for c in hydrated_citations],
        evidence=[EvidenceOut(**e) for e in hydrated_evidence],
        steps=result.steps,
        status=result.status,
    )


# ── Conversation archive endpoints ────────────────────────

@router.get("/conversations")
async def list_conversations(limit: int = 20):
    """List recent conversations."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a single conversation with its turns."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM conversation WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Conversation not found")
        turns = conn.execute(
            "SELECT * FROM conversation_turn_v2 WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return {**dict(row), "turns": [dict(t) for t in turns]}
    finally:
        conn.close()


@router.get("/conversations/{conversation_id}/turns")
async def get_conversation_turns(conversation_id: str):
    """Get turns for a conversation."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM conversation_turn_v2 WHERE conversation_id = ? ORDER BY created_at ASC",
            (conversation_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
