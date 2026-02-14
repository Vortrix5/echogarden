"""Continuous polling file-system watcher — asyncio background task."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from app.capture.config import (
    EG_MAX_FILE_BYTES,
    EG_POLL_INTERVAL,
    EG_WATCH_ROOTS,
)
from app.capture.hasher import detect_mime, sha256_file
from app.capture.repo import (
    enqueue_job,
    get_file_state,
    upsert_blob,
    upsert_file_state,
    upsert_source,
)

logger = logging.getLogger("echogarden.watcher")

# Directories to always skip (by name).
_IGNORED_DIRS: frozenset[str] = frozenset(
    {"__pycache__", ".git", ".svn", "node_modules", ".DS_Store"}
)


def _is_hidden(name: str) -> bool:
    return name.startswith(".")


def _walk_roots(roots: list[str]):
    """Yield (Path, os.stat_result) for every eligible file under *roots*."""
    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            logger.warning("Watch root does not exist: %s", root)
            continue
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune ignored / hidden directories in-place.
            dirnames[:] = [
                d
                for d in dirnames
                if not _is_hidden(d) and d not in _IGNORED_DIRS
            ]
            for fname in filenames:
                if _is_hidden(fname):
                    continue
                fpath = Path(dirpath) / fname
                try:
                    st = fpath.stat()
                except OSError:
                    continue
                yield fpath, st


def _format_size(n: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _process_file(fpath: Path, st: os.stat_result) -> None:
    """Check one file against file_state, hash it, upsert records, enqueue job."""
    path_str = str(fpath)
    mtime_ns = st.st_mtime_ns
    size_bytes = st.st_size

    # ── Step 1: Check file_state (dedup) ──────────────────
    existing = get_file_state(path_str)
    if existing and existing["mtime_ns"] == mtime_ns and existing["size_bytes"] == size_bytes:
        return  # unchanged

    change = "MODIFIED" if existing else "NEW"
    logger.info(
        "[DETECT] %s file: %s (%s)",
        change, path_str, _format_size(size_bytes),
    )

    # ── Step 2: Compute sha256 (streaming) ────────────────
    logger.info("[HASH]   Computing SHA-256 for %s …", fpath.name)
    sha = sha256_file(path_str)
    logger.info("[HASH]   sha256=%s…%s", sha[:12], sha[-8:])

    # ── Step 3: Upsert file_state ─────────────────────────
    upsert_file_state(path_str, mtime_ns, size_bytes, sha)
    logger.info("[STATE]  file_state upserted")

    # ── Step 4: Upsert SOURCE row ─────────────────────────
    source_id = upsert_source(uri=path_str, source_type="filesystem")
    logger.info("[SOURCE] source_id=%s (type=filesystem)", source_id[:12])

    # ── Step 5: Detect MIME ───────────────────────────────
    mime = detect_mime(path_str)
    logger.info("[MIME]   %s → %s", fpath.name, mime)

    # ── Step 6: Upsert BLOB row ───────────────────────────
    blob_id = upsert_blob(
        sha256=sha,
        path=path_str,
        mime=mime,
        size_bytes=size_bytes,
        source_id=source_id,
    )
    logger.info("[BLOB]   blob_id=%s", blob_id[:12])

    # ── Step 7: Enqueue ingest job ────────────────────────
    job_id = enqueue_job(
        job_type="ingest_blob",
        payload={
            "blob_id": blob_id,
            "source_id": source_id,
            "path": path_str,
            "sha256": sha,
            "mime": mime,
            "size_bytes": size_bytes,
        },
    )
    logger.info(
        "[JOB]    Enqueued ingest_blob job_id=%s for %s",
        job_id[:12], fpath.name,
    )
    logger.info(
        "[DONE]   Pipeline complete for %s — source=%s blob=%s job=%s",
        fpath.name, source_id[:8], blob_id[:8], job_id[:8],
    )


async def watch_loop() -> None:
    """Run forever: scan watch roots every EG_POLL_INTERVAL seconds."""
    logger.info(
        "Watcher started — roots=%s, interval=%ss", EG_WATCH_ROOTS, EG_POLL_INTERVAL
    )
    scan_count = 0
    while True:
        try:
            scan_count += 1
            await asyncio.to_thread(_scan_once, scan_count)
        except Exception:
            logger.exception("Watcher scan error")
        await asyncio.sleep(EG_POLL_INTERVAL)


def _scan_once(scan_number: int = 0) -> None:
    files_seen = 0
    files_changed = 0
    for fpath, st in _walk_roots(EG_WATCH_ROOTS):
        files_seen += 1
        try:
            existing = get_file_state(str(fpath))
            changed = not existing or existing["mtime_ns"] != st.st_mtime_ns or existing["size_bytes"] != st.st_size
            if changed:
                files_changed += 1
            _process_file(fpath, st)
        except Exception:
            logger.exception("Error processing %s", fpath)
    if files_changed > 0:
        logger.info(
            "[SCAN #%d] Scanned %d files — %d new/modified",
            scan_number, files_seen, files_changed,
        )
