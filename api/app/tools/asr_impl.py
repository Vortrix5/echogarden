"""asr_impl — transcribe audio via faster-whisper (local) or stub."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("echogarden.tools.asr")

_WHISPER_MODE = os.environ.get("EG_WHISPER_MODE", "local")
_MODELS_DIR = os.environ.get("EG_MODELS_DIR", "/data/models")
_WHISPER_CACHE = os.path.join(_MODELS_DIR, "whisper")
_WHISPER_MODEL_SIZE = os.environ.get("EG_WHISPER_MODEL", "base")

# Global singleton — loaded lazily
_model = None
_model_loaded = False


def _load_model():
    """Load faster-whisper model (singleton)."""
    global _model, _model_loaded
    if _model_loaded:
        return _model

    try:
        from faster_whisper import WhisperModel

        os.makedirs(_WHISPER_CACHE, exist_ok=True)
        logger.info("Loading faster-whisper model '%s' (cache=%s)...", _WHISPER_MODEL_SIZE, _WHISPER_CACHE)
        _model = WhisperModel(
            _WHISPER_MODEL_SIZE,
            device="cpu",
            compute_type="int8",
            download_root=_WHISPER_CACHE,
        )
        _model_loaded = True
        logger.info("Faster-whisper model loaded.")
        return _model
    except ImportError:
        logger.warning("faster-whisper not installed — ASR will use stub mode")
        _model_loaded = True
        return None
    except Exception:
        logger.exception("Failed to load faster-whisper model")
        _model_loaded = True
        return None


async def transcribe(audio_path: str) -> dict:
    """Transcribe an audio file. Returns dict with 'text' key.

    Modes:
      - local: uses faster-whisper (downloads model on first use)
      - stub:  returns placeholder text
    """
    if not os.path.isfile(audio_path):
        return {"text": f"[File not found: {audio_path}]"}

    if _WHISPER_MODE == "stub":
        logger.info("ASR stub mode — returning placeholder for %s", os.path.basename(audio_path))
        return {"text": f"(stub transcript for {os.path.basename(audio_path)})"}

    # Local mode — use faster-whisper
    import asyncio
    result = await asyncio.to_thread(_transcribe_sync, audio_path)
    return result


def _transcribe_sync(audio_path: str) -> dict:
    """Synchronous transcription via faster-whisper."""
    model = _load_model()
    if model is None:
        return {"text": f"(whisper unavailable — stub transcript for {os.path.basename(audio_path)})"}

    try:
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect
        )

        # Collect text from all segments
        texts = []
        for segment in segments:
            texts.append(segment.text.strip())

        full_text = " ".join(texts)
        logger.info(
            "Transcribed %s — %d chars, language=%s (prob=%.2f)",
            os.path.basename(audio_path), len(full_text),
            info.language, info.language_probability,
        )
        return {
            "text": full_text,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "duration_s": round(info.duration, 2),
        }
    except Exception as exc:
        logger.exception("Whisper transcription failed for %s", audio_path)
        return {"text": f"[Transcription error: {exc}]"}
