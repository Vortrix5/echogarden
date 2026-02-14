"""Streaming SHA-256 hashing and MIME type detection."""

from __future__ import annotations

import hashlib
import mimetypes

_CHUNK_SIZE = 1 << 16  # 64 KiB


def sha256_file(path: str) -> str:
    """Return the hex SHA-256 digest of a file, reading in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def detect_mime(path: str) -> str:
    """Return a MIME type string for the given path, or 'application/octet-stream'."""
    mime, _ = mimetypes.guess_type(path, strict=False)
    return mime or "application/octet-stream"
