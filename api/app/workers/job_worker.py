"""Continuous background job worker — asyncio task."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid

from app.capture.config import EG_MAX_FILE_BYTES, TEXT_EXTENSIONS
from app.capture.repo import claim_job, complete_job
from app.db.repo import insert_memory_card

logger = logging.getLogger("echogarden.worker")

_WORKER_SLEEP = 0.5  # seconds between polls when queue is empty


def _read_text_content(path: str, max_bytes: int = EG_MAX_FILE_BYTES) -> str:
    """Read text content from a file, truncating at max_bytes."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception as exc:
        return f"[Error reading file: {exc}]"


def _summarise_text(content: str, path: str) -> str:
    """Create a simple summary for text content."""
    lines = content.splitlines()
    n_lines = len(lines)
    n_chars = len(content)
    preview = content[:500].strip()
    if n_chars > 500:
        preview += "…"
    return (
        f"File: {os.path.basename(path)}\n"
        f"Lines: {n_lines} | Characters: {n_chars}\n\n"
        f"{preview}"
    )


def _format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _handle_ingest_blob(payload: dict) -> None:
    """Process a single ingest_blob job."""
    path: str = payload["path"]
    blob_id: str = payload["blob_id"]
    source_id: str = payload["source_id"]
    mime: str = payload.get("mime", "application/octet-stream")
    size_bytes: int = payload.get("size_bytes", 0)
    fname = os.path.basename(path)

    ext = os.path.splitext(path)[1].lower()
    is_text = ext in TEXT_EXTENSIONS
    too_large = size_bytes > EG_MAX_FILE_BYTES

    logger.info(
        "[PROCESS] %s — %s, %s, text=%s, oversized=%s",
        fname, mime, _format_size(size_bytes), is_text, too_large,
    )

    memory_id = uuid.uuid4().hex

    if is_text and not too_large:
        logger.info("[READ]    Reading text content from %s …", fname)
        content = _read_text_content(path)
        summary = _summarise_text(content, path)
        card_type = "file_capture"
        logger.info(
            "[CARD]    Creating memory_card type=%s (%d lines, %d chars)",
            card_type, len(content.splitlines()), len(content),
        )
    else:
        if too_large:
            reason = f"oversized ({_format_size(size_bytes)} > {EG_MAX_FILE_BYTES // (1024*1024)} MB)"
            summary = (
                f"Binary/large file captured; parsing pending.\n"
                f"File: {fname} | Size: {size_bytes} bytes | MIME: {mime}"
            )
        else:
            reason = f"binary ({mime})"
            summary = (
                f"Binary file captured; parsing pending.\n"
                f"File: {fname} | Size: {size_bytes} bytes | MIME: {mime}"
            )
        card_type = "file_capture_placeholder"
        logger.info(
            "[CARD]    Creating placeholder card — reason: %s", reason,
        )

    metadata = {
        "blob_id": blob_id,
        "source_id": source_id,
        "file_path": path,
        "mime": mime,
        "size_bytes": size_bytes,
    }

    insert_memory_card(
        memory_id=memory_id,
        card_type=card_type,
        summary=summary,
        metadata=metadata,
    )
    logger.info(
        "[DONE]    memory_card=%s type=%s for %s",
        memory_id[:12], card_type, fname,
    )


_JOB_HANDLERS = {
    "ingest_blob": _handle_ingest_blob,
}


async def worker_loop() -> None:
    """Run forever: claim and process jobs from the queue."""
    logger.info("Job worker started")
    jobs_processed = 0
    while True:
        try:
            job = await asyncio.to_thread(claim_job)
            if job is None:
                await asyncio.sleep(_WORKER_SLEEP)
                continue

            jobs_processed += 1
            job_id = job["job_id"]
            job_type = job["type"]
            payload = json.loads(job["payload_json"])

            logger.info(
                "[CLAIM]  Job #%d — id=%s type=%s",
                jobs_processed, job_id[:12], job_type,
            )

            handler = _JOB_HANDLERS.get(job_type)
            if handler is None:
                logger.warning("[SKIP]   Unknown job type: %s", job_type)
                await asyncio.to_thread(
                    complete_job, job_id, f"Unknown job type: {job_type}"
                )
                continue

            try:
                await asyncio.to_thread(handler, payload)
                await asyncio.to_thread(complete_job, job_id, None)
                logger.info("[OK]     Job %s completed successfully", job_id[:12])
            except Exception as exc:
                logger.exception("[FAIL]   Job %s failed: %s", job_id[:12], exc)
                await asyncio.to_thread(complete_job, job_id, str(exc))

        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(_WORKER_SLEEP)
