"""Phase 9 — Cards endpoints with filtering, search, detail, blob streaming, thumbnails, and open redirect."""

from __future__ import annotations

import hashlib
import json
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response

from app.db.conn import get_conn

router = APIRouter(tags=["cards"])

_THUMB_DIR = os.environ.get("EG_THUMB_DIR", "/data/thumbs")


@router.get("/cards")
async def list_cards(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source_type: str | None = Query(None),
    card_type: str | None = Query(None),
    q: str | None = Query(None),
):
    """List memory cards with optional filters and text search."""
    conn = get_conn()
    try:
        clauses: list[str] = []
        params: list = []

        if source_type:
            clauses.append("type = ?")
            params.append(source_type)
        if card_type:
            # card_type stored in metadata JSON
            clauses.append("json_extract(metadata, '$.card_type') = ?")
            params.append(card_type)
        if q:
            clauses.append("(summary LIKE ? OR content_text LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.extend([limit, offset])

        rows = conn.execute(
            f"SELECT * FROM memory_card{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [_card_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/cards/{memory_id}")
async def get_card(memory_id: str):
    """Get a single memory card by ID, enriched with source metadata."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM memory_card WHERE memory_id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Card not found")
        d = _card_dict(row)

        # Enrich with blob/source info for human-readable citations
        meta = d.get("metadata_json") or d.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        blob_id = meta.get("blob_id", "")
        file_path = meta.get("file_path", "")
        url = meta.get("url", "")

        # Resolve mime from blob table
        mime = meta.get("mime", "")
        if blob_id and not mime:
            blob_row = conn.execute("SELECT mime FROM blob WHERE blob_id = ?", (blob_id,)).fetchone()
            if blob_row:
                mime = blob_row["mime"] or ""

        d["title"] = (d.get("summary") or "")[:80] or memory_id[:16]
        d["file_path"] = file_path
        d["url"] = url
        d["blob_id"] = blob_id
        d["mime"] = mime
        d["media_url"] = f"/api/blobs/{blob_id}" if blob_id else ""
        d["thumb_url"] = (f"/api/blobs/{blob_id}/thumb?w=320&h=320"
                          if blob_id and mime.startswith("image/") else "")
        d["open_url"] = f"/api/cards/{memory_id}/open" if (blob_id or file_path) else ""

        return d
    finally:
        conn.close()


@router.get("/cards/{memory_id}/open")
async def open_card_source(memory_id: str):
    """Redirect to or stream the source file for a memory card."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT metadata, metadata_json FROM memory_card WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Card not found")

        meta = _parse_meta(row)
        blob_id = meta.get("blob_id", "")
        file_path = meta.get("file_path", "")
        url = meta.get("url", "")

        # Try blob first
        if blob_id:
            blob_row = conn.execute(
                "SELECT path, mime FROM blob WHERE blob_id = ?", (blob_id,)
            ).fetchone()
            if blob_row and blob_row["path"] and os.path.isfile(blob_row["path"]):
                return FileResponse(
                    blob_row["path"],
                    media_type=blob_row["mime"] or "application/octet-stream",
                    filename=os.path.basename(blob_row["path"]),
                )

        # Fall back to file_path
        if file_path and os.path.isfile(file_path):
            return FileResponse(file_path, filename=os.path.basename(file_path))

        # Fall back to URL redirect
        if url:
            return RedirectResponse(url)

        raise HTTPException(status_code=404, detail="No source file or URL found")
    finally:
        conn.close()


@router.get("/blobs/{blob_id}")
async def stream_blob(blob_id: str):
    """Stream a raw blob file by blob_id."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT path, mime FROM blob WHERE blob_id = ?", (blob_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Blob not found")
        if not row["path"] or not os.path.isfile(row["path"]):
            raise HTTPException(status_code=404, detail="Blob file missing on disk")
        return FileResponse(
            row["path"],
            media_type=row["mime"] or "application/octet-stream",
            filename=os.path.basename(row["path"]),
        )
    finally:
        conn.close()


@router.get("/blobs/{blob_id}/thumb")
async def blob_thumbnail(
    blob_id: str,
    w: int = Query(320, ge=32, le=1024),
    h: int = Query(320, ge=32, le=1024),
):
    """Return a resized thumbnail for an image blob. Cached on disk."""
    # Sanitise blob_id to prevent path traversal
    safe_id = blob_id.replace("/", "").replace("..", "")
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT path, mime FROM blob WHERE blob_id = ?", (safe_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Blob not found")
        src_path = row["path"]
        mime = row["mime"] or ""
        if not src_path or not os.path.isfile(src_path):
            raise HTTPException(status_code=404, detail="Blob file missing")
        if not mime.startswith("image/"):
            raise HTTPException(status_code=400, detail="Not an image blob")
    finally:
        conn.close()

    # Cache key
    cache_key = hashlib.md5(f"{safe_id}:{w}:{h}".encode()).hexdigest()
    os.makedirs(_THUMB_DIR, exist_ok=True)
    cache_path = os.path.join(_THUMB_DIR, f"{cache_key}.jpg")

    if not os.path.isfile(cache_path):
        try:
            from PIL import Image
            img = Image.open(src_path)
            img.thumbnail((w, h))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img.save(cache_path, "JPEG", quality=80)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Thumbnail generation failed: {exc}")

    return FileResponse(cache_path, media_type="image/jpeg")


def _parse_meta(row) -> dict:
    """Extract metadata dict from a row with metadata/metadata_json columns."""
    for key in ("metadata_json", "metadata"):
        val = row[key] if key in row.keys() else None
        if val and isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
        elif isinstance(val, dict):
            return val
    return {}


def _card_dict(row) -> dict:
    """Convert a sqlite3.Row to a clean dict, parsing JSON fields."""
    d = dict(row)
    for key in ("metadata", "metadata_json"):
        if key in d and isinstance(d[key], str):
            try:
                d[key] = json.loads(d[key])
            except (json.JSONDecodeError, TypeError):
                pass
    return d
