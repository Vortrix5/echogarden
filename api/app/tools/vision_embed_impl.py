"""vision_embed_impl — generate image embeddings via OpenCLIP + upsert to Qdrant."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger("echogarden.tools.vision_embed")

_OPENCLIP_MODE = os.environ.get("EG_OPENCLIP_MODE", "local")
_MODELS_DIR = os.environ.get("EG_MODELS_DIR", "/data/models")
_OPENCLIP_CACHE = os.path.join(_MODELS_DIR, "openclip")

_COLLECTION_NAME = "vision"

# Global singletons — loaded lazily
_model = None
_preprocess = None
_tokenizer = None
_model_loaded = False
_VECTOR_DIM = 512  # ViT-B-32 default


def _load_model():
    """Load OpenCLIP model (singleton)."""
    global _model, _preprocess, _tokenizer, _model_loaded, _VECTOR_DIM
    if _model_loaded:
        return _model

    try:
        import open_clip
        import torch

        os.makedirs(_OPENCLIP_CACHE, exist_ok=True)
        os.environ["OPEN_CLIP_CACHE_DIR"] = _OPENCLIP_CACHE

        model_name = "ViT-B-32"
        pretrained = "laion2b_s34b_b79k"

        logger.info("Loading OpenCLIP model %s/%s (cache=%s)...", model_name, pretrained, _OPENCLIP_CACHE)
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            model_name, pretrained=pretrained,
        )
        _tokenizer = open_clip.get_tokenizer(model_name)
        _model.eval()

        # Determine vector dimension from a dummy forward pass
        with torch.no_grad():
            dummy = torch.randn(1, 3, 224, 224)
            out = _model.encode_image(dummy)
            _VECTOR_DIM = out.shape[-1]

        _model_loaded = True
        logger.info("OpenCLIP model loaded (dim=%d).", _VECTOR_DIM)
        return _model
    except ImportError:
        logger.warning("open_clip_torch not installed — vision_embed will use stub mode")
        _model_loaded = True
        return None
    except Exception:
        logger.exception("Failed to load OpenCLIP model")
        _model_loaded = True
        return None


def _ensure_qdrant_collection():
    """Create the vision collection in Qdrant if missing."""
    from app.tools.qdrant_client import ensure_collection
    ensure_collection(_COLLECTION_NAME, _VECTOR_DIM)


async def embed_image(
    image_path: str,
    blob_id: str = "",
    memory_id: str = "",
    mime: str = "",
) -> dict:
    """Generate vision embedding and upsert to Qdrant.

    Returns dict with 'vector_ref' key like 'qdrant:vision:<point_id>'.
    """
    import asyncio

    if _OPENCLIP_MODE == "stub":
        import hashlib
        h = hashlib.sha256(image_path.encode()).hexdigest()[:12]
        return {"vector_ref": f"qdrant:stub:vision:{h}"}

    if not os.path.isfile(image_path):
        return {"vector_ref": "", "error": f"File not found: {image_path}"}

    result = await asyncio.to_thread(
        _embed_image_sync, image_path, blob_id, memory_id, mime
    )
    return result


def _embed_image_sync(
    image_path: str,
    blob_id: str,
    memory_id: str,
    mime: str,
) -> dict:
    """Synchronous image embedding + Qdrant upsert."""
    model = _load_model()
    if model is None:
        import hashlib
        h = hashlib.sha256(image_path.encode()).hexdigest()[:12]
        return {"vector_ref": f"qdrant:stub:vision:{h}"}

    try:
        import torch
        from PIL import Image

        img = Image.open(image_path).convert("RGB")
        img_tensor = _preprocess(img).unsqueeze(0)

        with torch.no_grad():
            features = model.encode_image(img_tensor)
            features = features / features.norm(dim=-1, keepdim=True)
            vector = features.squeeze().tolist()

        # Upsert to Qdrant
        _ensure_qdrant_collection()
        from app.tools.qdrant_client import upsert_point

        point_id = upsert_point(
            collection=_COLLECTION_NAME,
            vector=vector,
            payload={
                "memory_id": memory_id,
                "blob_id": blob_id,
                "modality": "vision",
                "source_type": "file",
                "mime": mime,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

        vector_ref = f"qdrant:vision:{point_id}"
        logger.info("Vision embedding upserted: %s (dim=%d)", vector_ref, len(vector))
        return {"vector_ref": vector_ref}

    except Exception as exc:
        logger.exception("Vision embedding failed for %s", image_path)
        return {"vector_ref": "", "error": str(exc)}
