"""Phase 5 — Hybrid retrieval service.

Merges:
  1) SQLite FTS  (lexical)
  2) Qdrant semantic search
  3) Graph expansion from top seeds
  4) Recency + source-type weighting

Each signal is normalised to [0, 1] and combined with configurable weights.
The service produces an explainability breakdown per result.
"""

from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from app.retrieval.graph_expand import GraphCandidate, expand_from_seeds
from app.retrieval.models import (
    GraphPath,
    RetrievedCard,
    RetrieveRequest,
    RetrieveResponse,
    SignalBreakdown,
)

logger = logging.getLogger("echogarden.retrieval.service")

# ── Scoring weights ──────────────────────────────────────
W_SEMANTIC = 0.45
W_FTS = 0.35
W_GRAPH = 0.15
W_RECENCY = 0.05

# ── Source-type boosts ───────────────────────────────────
_SOURCE_BOOSTS: dict[str, float] = {
    "browser_highlight": 0.10,
    "browser_bookmark": 0.05,
    "file_capture": 0.03,
    "audio_note": 0.03,
    "browser_visit": -0.10,
}

# ── Recency half-life (days) ─────────────────────────────
_RECENCY_HALFLIFE_DAYS = 30.0


# ── Public API ───────────────────────────────────────────


async def hybrid_retrieve(req: RetrieveRequest) -> RetrieveResponse:
    """Execute the full hybrid retrieval pipeline and return ranked results."""
    import asyncio

    candidates: dict[str, _Candidate] = {}

    # ── 1.  FTS ──────────────────────────────────────────
    fts_hits = await asyncio.to_thread(
        _fts_search, req.query, req.fts_k, req.time_min, req.time_max, req.source_types
    )
    for mid, score in fts_hits:
        _ensure(candidates, mid).fts_score = score
        _ensure(candidates, mid).reasons.add("fts_match")

    # ── 2.  Semantic search ──────────────────────────────
    if req.use_semantic:
        sem_hits = await _semantic_search(req.query, req.vec_k)
        for mid, score in sem_hits:
            _ensure(candidates, mid).semantic_score = score
            _ensure(candidates, mid).reasons.add("semantic_text")

    # ── 3.  Graph expansion from top seeds ───────────────
    if req.use_graph and req.hops > 0:
        # Pick seed_k best candidates so far by preliminary score
        seeds = _top_seed_ids(candidates, req.seed_k)
        if seeds:
            graph_hits = await asyncio.to_thread(
                expand_from_seeds, seeds, req.hops
            )
            for gc in graph_hits:
                c = _ensure(candidates, gc.memory_id)
                if gc.graph_score > c.graph_score:
                    c.graph_score = gc.graph_score
                    c.via_entity_ids = gc.via_entity_ids
                c.reasons.add("graph_expand")

    # ── 4.  Fetch card metadata for all candidates ───────
    all_ids = list(candidates.keys())
    cards_map = await asyncio.to_thread(_fetch_cards, all_ids)

    # ── 5.  Apply time / source filters, recency, source boost ─
    results: list[RetrievedCard] = []
    for mid, c in candidates.items():
        card = cards_map.get(mid)
        if card is None:
            continue  # dangling reference

        created_at = card.get("created_at")
        source_type = _resolve_source_type(card)

        # Filter: time window (normalize T vs space in ISO timestamps)
        created_at_cmp = created_at.replace(" ", "T") if created_at else None
        time_min_cmp = req.time_min.replace(" ", "T") if req.time_min else None
        time_max_cmp = req.time_max.replace(" ", "T") if req.time_max else None
        if time_min_cmp and created_at_cmp and created_at_cmp < time_min_cmp:
            continue
        if time_max_cmp and created_at_cmp and created_at_cmp > time_max_cmp:
            continue

        # Filter: source_types
        if req.source_types and source_type not in req.source_types:
            continue

        # Recency score
        recency = _recency_score(created_at)
        source_boost = _SOURCE_BOOSTS.get(source_type or "", 0.0)

        final = (
            W_SEMANTIC * c.semantic_score
            + W_FTS * c.fts_score
            + W_GRAPH * c.graph_score
            + W_RECENCY * recency
            + source_boost
        )
        final = max(0.0, min(1.0, final))

        reasons = sorted(c.reasons)
        graph_path = None
        if c.via_entity_ids:
            graph_path = GraphPath(via_entity_ids=c.via_entity_ids)

        # Phase 9 — derive media-first fields from card metadata
        meta_raw = card.get("metadata_json") or card.get("metadata")
        meta: dict[str, Any] = {}
        if meta_raw:
            try:
                meta = json.loads(meta_raw) if isinstance(meta_raw, str) else (meta_raw if isinstance(meta_raw, dict) else {})
            except Exception:
                meta = {}
        blob_id = meta.get("blob_id", "")
        file_path = meta.get("file_path", "")
        url = meta.get("url", "")
        mime = meta.get("mime", "")
        # Resolve mime from blob table if missing
        if blob_id and not mime:
            from app.db.conn import get_conn as _gc
            _cx = _gc()
            try:
                _br = _cx.execute("SELECT mime FROM blob WHERE blob_id = ?", (blob_id,)).fetchone()
                if _br:
                    mime = _br["mime"] or ""
            finally:
                _cx.close()
        title = _card_title(card.get("summary"), file_path, url, mid)
        media_url = f"/api/blobs/{blob_id}" if blob_id else ""
        thumb_url = (f"/api/blobs/{blob_id}/thumb?w=320&h=320"
                     if blob_id and mime.startswith("image/") else "")
        open_url = f"/api/cards/{mid}/open" if (blob_id or file_path) else ""

        results.append(
            RetrievedCard(
                memory_id=mid,
                summary=card.get("summary"),
                created_at=created_at,
                source_type=source_type,
                final_score=round(final, 6),
                signals=SignalBreakdown(
                    fts=round(c.fts_score, 6),
                    semantic=round(c.semantic_score, 6),
                    graph=round(c.graph_score, 6),
                    recency=round(recency, 6),
                    source_boost=round(source_boost, 6),
                ),
                reasons=reasons,
                graph_path=graph_path,
                title=title,
                mime=mime or None,
                media_url=media_url or None,
                thumb_url=thumb_url or None,
                open_url=open_url or None,
            )
        )

    results.sort(key=lambda r: r.final_score, reverse=True)

    # ── 6.  Filter out low-relevance noise ────────────────
    MIN_SCORE = 0.18
    results = [r for r in results if r.final_score >= MIN_SCORE]

    return RetrieveResponse(results=results[: req.top_k])


# ── Internal helpers ─────────────────────────────────────


class _Candidate:
    __slots__ = (
        "fts_score",
        "semantic_score",
        "graph_score",
        "via_entity_ids",
        "reasons",
    )

    def __init__(self) -> None:
        self.fts_score: float = 0.0
        self.semantic_score: float = 0.0
        self.graph_score: float = 0.0
        self.via_entity_ids: list[str] = []
        self.reasons: set[str] = set()


def _ensure(candidates: dict[str, _Candidate], mid: str) -> _Candidate:
    if mid not in candidates:
        candidates[mid] = _Candidate()
    return candidates[mid]


def _top_seed_ids(candidates: dict[str, _Candidate], k: int) -> list[str]:
    """Return top-k memory_ids ranked by preliminary (sem + fts) score."""
    scored = [
        (mid, c.semantic_score * W_SEMANTIC + c.fts_score * W_FTS)
        for mid, c in candidates.items()
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [mid for mid, _ in scored[:k]]


# ── FTS ──────────────────────────────────────────────────


def _fts_search(
    query: str,
    limit: int,
    time_min: str | None,
    time_max: str | None,
    source_types: list[str] | None,
) -> list[tuple[str, float]]:
    """Run FTS5 search and return (memory_id, normalised_score) pairs."""
    from app.db.repo import search_fts_phase5

    return search_fts_phase5(query, limit, time_min, time_max, source_types)


# ── Semantic search ──────────────────────────────────────


async def _semantic_search(query: str, limit: int) -> list[tuple[str, float]]:
    """Encode the query with the same model used at ingestion and search Qdrant."""
    from app.tools.qdrant_client import search_text_vectors

    import asyncio

    return await asyncio.to_thread(search_text_vectors, query, limit)


# ── Card fetching ────────────────────────────────────────


def _fetch_cards(memory_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Bulk-fetch memory cards from SQLite."""
    if not memory_ids:
        return {}
    from app.db.repo import fetch_memory_cards_by_ids

    cards = fetch_memory_cards_by_ids(memory_ids)
    return {c["memory_id"]: c for c in cards}


# ── Recency scoring ─────────────────────────────────────


def _recency_score(created_at: str | None) -> float:
    """exp(-days_ago / 30), clamped to [0, 1]."""
    if not created_at:
        return 0.0
    try:
        dt = datetime.fromisoformat(created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days_ago = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        if days_ago < 0:
            days_ago = 0.0
        score = math.exp(-days_ago / _RECENCY_HALFLIFE_DAYS)
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


# ── Source type resolution ───────────────────────────────


def _resolve_source_type(card: dict[str, Any]) -> str | None:
    """Extract source_type from card dict, checking type, then metadata_json."""
    st = card.get("type") or card.get("source_type")
    if st:
        return st
    meta_raw = card.get("metadata_json") or card.get("metadata")
    if meta_raw:
        try:
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            return meta.get("source_type")
        except Exception:
            pass
    return None


def _card_title(summary: str | None, file_path: str, url: str, mid: str) -> str:
    """Derive a short human-readable title for a retrieved card."""
    if file_path:
        return os.path.basename(file_path)
    if url:
        from urllib.parse import urlparse
        try:
            host = urlparse(url).hostname or url[:40]
            return host
        except Exception:
            return url[:40]
    if summary:
        return summary[:60].rstrip()
    return mid[:16]
