"""Phase 5 — POST /retrieve   hybrid retrieval endpoint + search history."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.db.conn import get_conn
from app.retrieval.models import RetrieveRequest, RetrieveResponse
from app.retrieval.service import hybrid_retrieve

logger = logging.getLogger("echogarden.routers.retrieve")

router = APIRouter(tags=["retrieval"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest) -> RetrieveResponse:
    """Hybrid retrieval: FTS + semantic + graph expand + recency + source boost.

    Returns top_k memory cards ranked by merged score with explainability.
    Also persists the search query to search_query table for history.
    """
    resp = await hybrid_retrieve(body)

    # Persist search history
    try:
        conn = get_conn()
        try:
            search_id = uuid.uuid4().hex
            filters = {}
            if body.source_types:
                filters["source_types"] = body.source_types
            if body.time_min:
                filters["time_min"] = body.time_min
            if body.time_max:
                filters["time_max"] = body.time_max

            # Dedup: if same literal query exists, just update it
            existing = conn.execute(
                "SELECT search_id FROM search_query WHERE query_text = ? LIMIT 1",
                (body.query,),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE search_query SET result_count = ?, created_at = ? WHERE search_id = ?",
                    (len(resp.results), _now_iso(), existing["search_id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO search_query
                       (search_id, query_text, filters_json, result_count, created_at)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        search_id,
                        body.query,
                        json.dumps(filters) if filters else None,
                        len(resp.results),
                        _now_iso(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.debug("Failed to persist search history", exc_info=True)

    return resp


@router.get("/search/history")
async def search_history(limit: int = Query(20, ge=1, le=100)):
    """Return recent search queries."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM search_query ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("filters_json") and isinstance(d["filters_json"], str):
                try:
                    d["filters_json"] = json.loads(d["filters_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results
    finally:
        conn.close()
