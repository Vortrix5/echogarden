"""image_caption_impl — generate a short caption for an image.

Primary: BLIP (Salesforce/blip-image-captioning-base) — a generative
vision-language model that produces natural-language captions.
Fallback 1: OpenCLIP zero-shot classification.
Fallback 2: filename + dimensions heuristic.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("echogarden.tools.image_caption")

_MAX_CAPTION_LEN = 300

_MODELS_DIR = os.environ.get("EG_MODELS_DIR", "/data/models")
_BLIP_CACHE = os.path.join(_MODELS_DIR, "blip")
_BLIP_MODEL_NAME = "Salesforce/blip-image-captioning-base"

# ── BLIP singleton ────────────────────────────────────────

_blip_model = None
_blip_processor = None
_blip_loaded = False


def _load_blip():
    """Load BLIP model + processor (singleton, lazy)."""
    global _blip_model, _blip_processor, _blip_loaded
    if _blip_loaded:
        return _blip_model, _blip_processor

    try:
        import torch
        from transformers import BlipProcessor, BlipForConditionalGeneration

        os.makedirs(_BLIP_CACHE, exist_ok=True)

        # Check if already cached locally
        cache_marker = os.path.join(
            _BLIP_CACHE,
            f"models--{_BLIP_MODEL_NAME.replace('/', '--')}",
            "snapshots",
        )
        local_only = os.path.isdir(cache_marker) and len(os.listdir(cache_marker)) > 0

        if local_only:
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            logger.info("BLIP cache found — loading in offline mode")
        else:
            # Need to download — clear all offline flags so HF Hub allows network access.
            # docker-compose sets these as env vars; os.environ.pop removes them
            # for the current process. Also reset huggingface_hub internal state.
            os.environ.pop("HF_HUB_OFFLINE", None)
            os.environ.pop("TRANSFORMERS_OFFLINE", None)
            try:
                import huggingface_hub.constants
                huggingface_hub.constants.HF_HUB_OFFLINE = False
            except Exception:
                pass
            logger.info("BLIP cache not found at %s — downloading model (this may take a few minutes) ...", _BLIP_CACHE)

        logger.info("Loading BLIP model '%s' (cache=%s, local_only=%s) ...", _BLIP_MODEL_NAME, _BLIP_CACHE, local_only)
        _blip_processor = BlipProcessor.from_pretrained(
            _BLIP_MODEL_NAME,
            cache_dir=_BLIP_CACHE,
            local_files_only=local_only,
        )
        _blip_model = BlipForConditionalGeneration.from_pretrained(
            _BLIP_MODEL_NAME,
            cache_dir=_BLIP_CACHE,
            local_files_only=local_only,
            torch_dtype=torch.float32,
        )
        _blip_model.eval()
        _blip_loaded = True
        logger.info("BLIP model loaded successfully.")

        # Restore offline flags so other models don't accidentally download
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

        return _blip_model, _blip_processor

    except ImportError:
        logger.warning("transformers not installed — BLIP captioning unavailable")
        _blip_loaded = True  # permanent
        return None, None
    except Exception:
        logger.warning("Failed to load BLIP model — will retry next call", exc_info=True)
        return None, None


def _caption_with_blip(image_path: str) -> dict | None:
    """Generate a real natural-language caption with BLIP.

    Returns dict with keys: caption — or None on failure.
    """
    try:
        import torch
        from PIL import Image

        model, processor = _load_blip()
        if model is None or processor is None:
            return None

        img = Image.open(image_path).convert("RGB")

        # Unconditional captioning
        inputs = processor(images=img, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=60,
                num_beams=4,
                early_stopping=True,
            )
        caption = processor.decode(out[0], skip_special_tokens=True).strip()

        # Also try a conditional prompt for more detail
        conditional_prompt = "a detailed image of"
        cond_inputs = processor(images=img, text=conditional_prompt, return_tensors="pt")
        with torch.no_grad():
            cond_out = model.generate(
                **cond_inputs,
                max_new_tokens=60,
                num_beams=4,
                early_stopping=True,
            )
        cond_caption = processor.decode(cond_out[0], skip_special_tokens=True).strip()

        # Use whichever is longer / more descriptive
        best_caption = cond_caption if len(cond_caption) > len(caption) else caption

        logger.info(
            "BLIP caption for %s: %s",
            os.path.basename(image_path), best_caption[:120],
        )
        return {
            "caption": best_caption[:_MAX_CAPTION_LEN],
        }

    except Exception:
        logger.warning("BLIP caption failed", exc_info=True)
        return None

# ── Zero-shot label sets ──────────────────────────────────

_SUBJECT_LABELS = [
    # Animals
    "dog", "cat", "bird", "fish", "horse", "cow", "sheep", "rabbit",
    "deer", "bear", "lion", "tiger", "elephant", "monkey", "insect",
    "butterfly", "snake", "frog", "turtle", "hamster", "parrot",
    # People & activities
    "person", "people", "child", "baby", "man", "woman", "group of people",
    # Vehicles
    "car", "truck", "bicycle", "motorcycle", "airplane", "boat", "train", "bus",
    # Nature
    "flower", "tree", "mountain", "ocean", "beach", "river", "lake",
    "forest", "garden", "sunset", "sky", "clouds",
    # Built environment
    "house", "building", "bridge", "road", "city skyline", "office",
    "church", "castle", "skyscraper", "street",
    # Objects
    "food", "book", "computer", "phone", "furniture", "toy",
    "musical instrument", "sports equipment", "artwork", "sculpture",
    # Documents / text
    "document", "screenshot", "diagram", "chart", "map", "handwriting",
    "whiteboard", "presentation slide", "receipt", "form",
]

_SCENE_LABELS = [
    "indoors", "outdoors", "close-up", "aerial view",
    "daytime", "nighttime", "underwater",
]

_STYLE_LABELS = [
    "photograph", "illustration", "painting", "sketch",
    "digital art", "meme", "infographic",
]


def _caption_with_clip(image_path: str) -> dict | None:
    """Generate a descriptive caption via OpenCLIP zero-shot classification.

    Returns dict with keys: caption, subjects, scene, style — or None if
    OpenCLIP is unavailable.
    """
    try:
        import torch
        from PIL import Image
        import app.tools.vision_embed_impl as _vmod

        model = _vmod._load_model()
        preprocess = _vmod._preprocess
        tokenizer = _vmod._tokenizer

        if model is None or preprocess is None or tokenizer is None:
            return None

        img = Image.open(image_path).convert("RGB")
        img_tensor = preprocess(img).unsqueeze(0)

        def _classify(labels: list[str], prompt_prefix: str = "a photo of ") -> list[tuple[str, float]]:
            prompts = [f"{prompt_prefix}{l}" for l in labels]
            tokens = tokenizer(prompts)
            with torch.no_grad():
                img_feat = model.encode_image(img_tensor)
                txt_feat = model.encode_text(tokens)
                img_feat = img_feat / img_feat.norm(dim=-1, keepdim=True)
                txt_feat = txt_feat / txt_feat.norm(dim=-1, keepdim=True)
                sims = (img_feat @ txt_feat.T).squeeze().tolist()
            if isinstance(sims, float):
                sims = [sims]
            return sorted(zip(labels, sims), key=lambda x: -x[1])

        # Get top subjects, scene, and style
        subjects = _classify(_SUBJECT_LABELS, "a photo of a ")
        scenes = _classify(_SCENE_LABELS, "a photo taken ")
        styles = _classify(_STYLE_LABELS, "")

        top_subject = subjects[0][0]
        top_subject_score = subjects[0][1]
        second_subject = subjects[1][0] if len(subjects) > 1 else None
        second_score = subjects[1][1] if len(subjects) > 1 else 0.0
        top_scene = scenes[0][0]
        top_style = styles[0][0]

        # Build descriptive caption
        parts = []

        # Style (only if not "photograph" which is default)
        if top_style != "photograph":
            parts.append(f"{top_style} of")
        else:
            parts.append("Photo of")

        # Main subject
        article = "an" if top_subject[0] in "aeiou" else "a"
        parts.append(f"{article} {top_subject}")

        # Second subject if close enough in score
        if second_subject and second_score > top_subject_score * 0.85:
            parts.append(f"and {second_subject}")

        # Scene context
        parts.append(f"({top_scene})")

        caption = " ".join(parts)

        # Collect detected subjects with confidence (top-N above threshold)
        _MIN_ENTITY_SCORE = 0.20
        detected_subjects = [
            {"name": label, "confidence": round(score, 3)}
            for label, score in subjects
            if score >= _MIN_ENTITY_SCORE
        ][:5]  # max 5 subjects

        # Scene and style as tags
        detected_tags = [top_scene, top_style]
        if second_subject and second_score > top_subject_score * 0.85:
            detected_tags.append(second_subject)

        logger.info(
            "CLIP caption for %s (score=%.3f): %s | subjects=%s",
            os.path.basename(image_path), top_subject_score, caption,
            [s["name"] for s in detected_subjects],
        )
        return {
            "caption": caption[:_MAX_CAPTION_LEN],
            "subjects": detected_subjects,
            "scene": top_scene,
            "style": top_style,
            "tags": detected_tags,
        }

    except Exception:
        logger.warning("CLIP caption failed", exc_info=True)
        return None


def _caption_heuristic(image_path: str) -> str:
    """Generate a heuristic caption from filename + image metadata.

    Does NOT hallucinate content — only uses verifiable information.
    """
    from PIL import Image

    basename = Path(image_path).stem
    clean_name = basename.replace("-", " ").replace("_", " ").replace(".", " ").strip()

    try:
        img = Image.open(image_path)
        width, height = img.size
        fmt = img.format or Path(image_path).suffix.lstrip(".").upper()

        exif_info = ""
        try:
            exif = img._getexif()  # type: ignore[attr-defined]
            if exif:
                make = exif.get(271, "")
                model = exif.get(272, "")
                if make or model:
                    camera = f"{make} {model}".strip()
                    exif_info = f", camera: {camera}"
        except Exception:
            pass

        caption = f"Image: {clean_name} ({fmt}, {width}x{height}{exif_info})"
    except Exception:
        caption = f"Image file: {clean_name}"

    return caption[:_MAX_CAPTION_LEN]


async def generate_caption(image_path: str) -> dict:
    """Generate a caption for an image.

    Returns:
      {
        "caption": "...",
        "model": "clip" | "heuristic",
        "status": "success" | "failed"
      }
    """
    import asyncio

    if not os.path.isfile(image_path):
        return {
            "caption": "",
            "model": "none",
            "status": "failed",
            "error": f"File not found: {image_path}",
        }

    try:
        result = await asyncio.to_thread(_generate_caption_sync, image_path)
        return result
    except Exception as exc:
        logger.exception("Caption generation failed for %s", image_path)
        return {
            "caption": "",
            "model": "none",
            "status": "failed",
            "error": str(exc),
        }


def _generate_caption_sync(image_path: str) -> dict:
    """Synchronous caption generation. Tries BLIP → CLIP → heuristic."""
    # 1. Try BLIP generative captioning (best quality)
    blip_result = _caption_with_blip(image_path)
    if blip_result:
        return {
            "caption": blip_result["caption"],
            "model": "blip",
            "status": "success",
            "subjects": [],
            "scene": "",
            "style": "",
            "tags": [],
        }

    # 2. Try OpenCLIP zero-shot (fallback)
    clip_result = _caption_with_clip(image_path)
    if clip_result:
        return {
            "caption": clip_result["caption"],
            "model": "clip",
            "status": "success",
            "subjects": clip_result["subjects"],
            "scene": clip_result["scene"],
            "style": clip_result["style"],
            "tags": clip_result["tags"],
        }

    # 3. Heuristic fallback
    caption = _caption_heuristic(image_path)
    logger.info("Heuristic caption for %s: %s", os.path.basename(image_path), caption[:80])
    return {
        "caption": caption,
        "model": "heuristic",
        "status": "success",
        "subjects": [],
        "scene": "",
        "style": "",
        "tags": [],
    }
