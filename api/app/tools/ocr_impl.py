"""ocr_impl — extract text from images via Tesseract."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

logger = logging.getLogger("echogarden.tools.ocr")

_TESSERACT_BIN = shutil.which("tesseract") or "tesseract"
_TIMEOUT = 30  # seconds


async def extract_text(image_path: str) -> dict:
    """Run Tesseract OCR on an image file and return extracted text.

    Returns dict with keys: text, confidence (placeholder).
    """
    if not os.path.isfile(image_path):
        return {"text": f"[File not found: {image_path}]"}

    try:
        proc = await asyncio.create_subprocess_exec(
            _TESSERACT_BIN, image_path, "stdout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_TIMEOUT
        )

        if proc.returncode != 0:
            err_msg = stderr.decode(errors="replace").strip()
            logger.warning("Tesseract failed (rc=%d): %s", proc.returncode, err_msg[:200])
            return {"text": f"[OCR error: {err_msg[:200]}]"}

        text = stdout.decode(errors="replace").strip()
        logger.info("OCR extracted %d chars from %s", len(text), os.path.basename(image_path))
        return {"text": text}

    except asyncio.TimeoutError:
        logger.warning("Tesseract timed out after %ds for %s", _TIMEOUT, image_path)
        return {"text": "[OCR timeout]"}
    except FileNotFoundError:
        logger.error("Tesseract binary not found at %s", _TESSERACT_BIN)
        return {"text": "[Tesseract not installed]"}
    except Exception as exc:
        logger.exception("OCR failed for %s", image_path)
        return {"text": f"[OCR error: {exc}]"}
