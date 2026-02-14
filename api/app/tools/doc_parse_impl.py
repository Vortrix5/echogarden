"""doc_parse_impl — extract text from documents via Apache Tika."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("echogarden.tools.doc_parse")

TIKA_URL = os.environ.get("TIKA_URL", "http://tika:9998")
_TIMEOUT = 30.0  # seconds


async def parse_document(path: str, blob_id: str = "") -> dict:
    """Send a file to Tika and return extracted text + detected mime.

    For text-like files that cannot be sent to Tika (e.g. plain .txt),
    we fall back to direct file reading.
    """
    _TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json"}
    ext = os.path.splitext(path)[1].lower()

    # For simple text files, read directly instead of going through Tika
    if ext in _TEXT_EXTENSIONS or path == "<inline>":
        return await _read_text_file(path)

    # Send binary to Tika
    if not os.path.isfile(path):
        return {"content_text": f"[File not found: {path}]", "mime": "text/plain"}

    try:
        file_size = os.path.getsize(path)
        if file_size == 0:
            return {"content_text": "", "mime": "text/plain"}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            with open(path, "rb") as f:
                content = f.read()

            # PUT /tika returns extracted text
            r = await client.put(
                f"{TIKA_URL}/tika",
                content=content,
                headers={
                    "Accept": "text/plain",
                    "Content-Disposition": f'attachment; filename="{os.path.basename(path)}"',
                },
            )
            r.raise_for_status()
            extracted_text = r.text.strip()

            # Detect MIME via /detect
            try:
                mime_r = await client.put(
                    f"{TIKA_URL}/detect/stream",
                    content=content,
                    headers={"Content-Disposition": f'attachment; filename="{os.path.basename(path)}"'},
                )
                detected_mime = mime_r.text.strip() if mime_r.status_code == 200 else "application/octet-stream"
            except Exception:
                detected_mime = "application/octet-stream"

        logger.info(
            "Tika parsed %s — %d chars, detected mime=%s",
            os.path.basename(path), len(extracted_text), detected_mime,
        )
        return {"content_text": extracted_text, "mime": detected_mime}

    except httpx.ConnectError:
        logger.warning("Tika unavailable at %s — falling back to direct read", TIKA_URL)
        return await _read_text_file(path)
    except Exception as exc:
        logger.exception("Tika parsing failed for %s", path)
        # Partial success: try direct read as fallback
        try:
            return await _read_text_file(path)
        except Exception:
            return {"content_text": f"[Parse error: {exc}]", "mime": "text/plain"}


async def _read_text_file(path: str) -> dict:
    """Fallback: read file content directly as UTF-8."""
    if path == "<inline>":
        return {"content_text": "", "mime": "text/plain"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(20 * 1024 * 1024)  # 20MB limit
        return {"content_text": text, "mime": "text/plain"}
    except Exception as exc:
        return {"content_text": f"[Read error: {exc}]", "mime": "text/plain"}
