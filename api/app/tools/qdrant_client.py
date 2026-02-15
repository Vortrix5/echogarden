"""Minimal Qdrant HTTP client — collection management + upsert + search."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from app.core.config import QDRANT_URL

logger = logging.getLogger("echogarden.qdrant")

_TIMEOUT = 30.0  # seconds


def _url(path: str) -> str:
    return f"{QDRANT_URL}{path}"


# ── Collection management ─────────────────────────────────

def ensure_collection(name: str, vector_size: int, distance: str = "Cosine") -> None:
    """Create collection if it does not already exist."""
    try:
        r = httpx.get(_url(f"/collections/{name}"), timeout=_TIMEOUT)
        if r.status_code == 200:
            return  # already exists
    except Exception:
        pass

    body = {
        "vectors": {
            "size": vector_size,
            "distance": distance,
        }
    }
    try:
        r = httpx.put(_url(f"/collections/{name}"), json=body, timeout=_TIMEOUT)
        r.raise_for_status()
        logger.info("Created Qdrant collection '%s' (dim=%d)", name, vector_size)
    except httpx.HTTPStatusError as exc:
        # 409 = already exists (race condition), that's fine
        if exc.response.status_code == 409:
            return
        raise
    except Exception:
        logger.exception("Failed to create Qdrant collection '%s'", name)
        raise


# ── Upsert ────────────────────────────────────────────────

def upsert_point(
    collection: str,
    vector: list[float],
    payload: dict[str, Any],
    point_id: str | None = None,
) -> str:
    """Upsert a single point. Returns the point_id."""
    pid = point_id or uuid.uuid4().hex
    body = {
        "points": [
            {
                "id": pid,
                "vector": vector,
                "payload": payload,
            }
        ]
    }
    r = httpx.put(
        _url(f"/collections/{collection}/points"),
        json=body,
        timeout=_TIMEOUT,
        params={"wait": "true"},
    )
    r.raise_for_status()
    return pid


# ── Search ────────────────────────────────────────────────

def search(
    collection: str,
    vector: list[float],
    limit: int = 10,
    score_threshold: float | None = None,
    filter_payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Search for nearest neighbors. Returns list of {id, score, payload}."""
    body: dict[str, Any] = {
        "vector": vector,
        "limit": limit,
        "with_payload": True,
    }
    if score_threshold is not None:
        body["score_threshold"] = score_threshold
    if filter_payload:
        body["filter"] = filter_payload

    try:
        r = httpx.post(
            _url(f"/collections/{collection}/points/search"),
            json=body,
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        results = []
        for hit in data.get("result", []):
            results.append({
                "id": hit["id"],
                "score": hit["score"],
                "payload": hit.get("payload", {}),
            })
        return results
    except Exception:
        logger.exception("Qdrant search failed on collection '%s'", collection)
        return []


def collection_exists(name: str) -> bool:
    """Check if a collection exists."""
    try:
        r = httpx.get(_url(f"/collections/{name}"), timeout=_TIMEOUT)
        return r.status_code == 200
    except Exception:
        return False


# ── Phase 5: text-vector search for hybrid retrieval ─────

def search_text_vectors(
    query: str,
    limit: int = 50,
) -> list[tuple[str, float]]:
    """Encode *query* with the same sentence-transformer model used at
    ingestion time, then search the ``text`` collection in Qdrant.

    Returns ``[(memory_id, normalised_sim_score), ...]`` sorted descending.
    Cosine similarity is already in [0, 1] for normalised embeddings.
    """
    try:
        from app.tools.text_embed_impl import _load_model

        model = _load_model()
        if model is None:
            return []

        vector = model.encode(query, normalize_embeddings=True).tolist()

        hits = search(
            collection="text",
            vector=vector,
            limit=limit,
        )

        results: list[tuple[str, float]] = []
        for hit in hits:
            mid = hit.get("payload", {}).get("memory_id")
            if not mid:
                continue
            score = float(hit.get("score", 0.0))
            # Clamp to [0, 1]
            score = max(0.0, min(1.0, score))
            results.append((mid, score))
        return results
    except Exception:
        logger.exception("search_text_vectors failed")
        return []
