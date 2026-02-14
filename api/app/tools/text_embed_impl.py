"""text_embed_impl — generate text embeddings via sentence-transformers + upsert to Qdrant."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("echogarden.tools.text_embed")

_MODELS_DIR = os.environ.get("EG_MODELS_DIR", "/data/models")
_ST_CACHE = os.path.join(_MODELS_DIR, "sentence_transformers")
_MODEL_NAME = os.environ.get("EG_TEXT_EMBED_MODEL", "all-MiniLM-L6-v2")

_COLLECTION_NAME = "text"

# Global singleton — loaded lazily
_model = None
_model_loaded = False
_VECTOR_DIM = 384  # all-MiniLM-L6-v2 default


def _load_model():
    """Load sentence-transformers model (singleton)."""
    global _model, _model_loaded, _VECTOR_DIM
    if _model_loaded:
        return _model

    try:
        from sentence_transformers import SentenceTransformer

        os.makedirs(_ST_CACHE, exist_ok=True)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = _ST_CACHE

        logger.info("Loading sentence-transformers model '%s' (cache=%s)...", _MODEL_NAME, _ST_CACHE)
        _model = SentenceTransformer(_MODEL_NAME, cache_folder=_ST_CACHE)
        _VECTOR_DIM = _model.get_sentence_embedding_dimension()
        _model_loaded = True
        logger.info("Sentence-transformers model loaded (dim=%d).", _VECTOR_DIM)
        return _model
    except ImportError:
        logger.warning("sentence-transformers not installed — text_embed will use stub mode")
        _model_loaded = True
        return None
    except Exception:
        logger.exception("Failed to load sentence-transformers model")
        _model_loaded = True
        return None


def _ensure_qdrant_collection():
    """Create the text collection in Qdrant if missing."""
    from app.tools.qdrant_client import ensure_collection
    ensure_collection(_COLLECTION_NAME, _VECTOR_DIM)


async def embed_text(
    text: str,
    memory_id: str = "",
    source_type: str = "file",
) -> dict:
    """Generate text embedding and upsert to Qdrant.

    Returns dict with 'vector_ref' key like 'qdrant:text:<point_id>'.
    """
    import asyncio

    if not text or not text.strip():
        return {"vector_ref": ""}

    result = await asyncio.to_thread(_embed_text_sync, text, memory_id, source_type)
    return result


def _embed_text_sync(text: str, memory_id: str, source_type: str) -> dict:
    """Synchronous text embedding + Qdrant upsert."""
    model = _load_model()
    if model is None:
        import hashlib
        h = hashlib.sha256(text.encode()).hexdigest()[:12]
        return {"vector_ref": f"qdrant:stub:text:{h}"}

    try:
        # Truncate to reasonable length for the model
        max_len = 8192
        truncated = text[:max_len] if len(text) > max_len else text

        vector = model.encode(truncated, normalize_embeddings=True).tolist()

        # Upsert to Qdrant
        _ensure_qdrant_collection()
        from app.tools.qdrant_client import upsert_point

        point_id = upsert_point(
            collection=_COLLECTION_NAME,
            vector=vector,
            payload={
                "memory_id": memory_id,
                "modality": "text",
                "source_type": source_type,
                "text_preview": truncated[:200],
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

        vector_ref = f"qdrant:text:{point_id}"
        logger.info("Text embedding upserted: %s (dim=%d)", vector_ref, len(vector))
        return {"vector_ref": vector_ref}

    except Exception as exc:
        logger.exception("Text embedding failed")
        return {"vector_ref": "", "error": str(exc)}


async def search_text(query: str, limit: int = 10) -> list[dict]:
    """Search for similar text embeddings in Qdrant."""
    import asyncio
    return await asyncio.to_thread(_search_text_sync, query, limit)


def _search_text_sync(query: str, limit: int) -> list[dict]:
    """Synchronous text search."""
    model = _load_model()
    if model is None:
        return []

    try:
        vector = model.encode(query, normalize_embeddings=True).tolist()
        _ensure_qdrant_collection()
        from app.tools.qdrant_client import search
        return search(_COLLECTION_NAME, vector, limit=limit)
    except Exception:
        logger.exception("Text search failed")
        return []
