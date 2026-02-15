"""ocr_impl — extract text from images via Tesseract.

Returns structured output:
  {
    "text": "...",           # extracted text (always a string, never error msgs)
    "status": "success"|"failed",
    "error": "..."|null,     # error message if status==failed
    "avg_confidence": float|null
  }
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil

logger = logging.getLogger("echogarden.tools.ocr")

_TESSERACT_BIN = shutil.which("tesseract") or "tesseract"
_TIMEOUT = 30  # seconds


def _ocr_success(text: str, avg_confidence: float | None = None) -> dict:
    return {
        "text": text,
        "status": "success",
        "error": None,
        "avg_confidence": avg_confidence,
    }


def _ocr_failed(error: str) -> dict:
    return {
        "text": "",
        "status": "failed",
        "error": error,
        "avg_confidence": None,
    }


async def _run_tesseract_tsv(image_path: str) -> tuple[str, float | None]:
    """Run Tesseract with TSV output to get per-word confidence.

    Returns (text, avg_confidence).
    """
    proc = await asyncio.create_subprocess_exec(
        _TESSERACT_BIN, image_path, "stdout", "--psm", "3", "-c", "tessedit_create_tsv=1",
        "tsv",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)

    if proc.returncode != 0:
        return "", None

    lines = stdout.decode(errors="replace").strip().split("\n")
    words: list[str] = []
    confidences: list[float] = []

    for line in lines[1:]:  # skip header
        parts = line.split("\t")
        if len(parts) >= 12:
            conf_str = parts[10]
            word = parts[11].strip()
            if word and conf_str not in ("-1", ""):
                words.append(word)
                try:
                    confidences.append(float(conf_str))
                except ValueError:
                    pass

    text = " ".join(words)
    avg_conf = sum(confidences) / len(confidences) if confidences else None
    return text, avg_conf


async def extract_text(image_path: str) -> dict:
    """Run Tesseract OCR on an image file and return structured output.

    Never returns error messages as text content. Errors go to the 'error' field.
    """
    if not os.path.isfile(image_path):
        return _ocr_failed(f"File not found: {image_path}")

    try:
        # Try TSV mode first for confidence scores
        try:
            text, avg_confidence = await _run_tesseract_tsv(image_path)
            if text:
                logger.info(
                    "OCR extracted %d chars (avg_conf=%.1f) from %s",
                    len(text), avg_confidence or 0, os.path.basename(image_path),
                )
                return _ocr_success(text, avg_confidence)
        except Exception:
            pass  # Fall through to plain mode

        # Plain stdout mode as fallback
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
            return _ocr_failed(f"Tesseract exit code {proc.returncode}: {err_msg[:200]}")

        text = stdout.decode(errors="replace").strip()
        logger.info("OCR extracted %d chars from %s", len(text), os.path.basename(image_path))
        return _ocr_success(text, avg_confidence=None)

    except asyncio.TimeoutError:
        logger.warning("Tesseract timed out after %ds for %s", _TIMEOUT, image_path)
        return _ocr_failed(f"Tesseract timed out after {_TIMEOUT}s")
    except FileNotFoundError:
        logger.error("Tesseract binary not found at %s", _TESSERACT_BIN)
        return _ocr_failed("Tesseract binary not installed")
    except Exception as exc:
        logger.exception("OCR failed for %s", image_path)
        return _ocr_failed(str(exc))
