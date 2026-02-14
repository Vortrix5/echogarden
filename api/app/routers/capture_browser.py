"""Browser capture endpoints — highlight, bookmark, research session, visit, import_history."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.capture.repo import upsert_source, enqueue_job
from app.db import repo as db_repo

logger = logging.getLogger("echogarden.capture.browser")

router = APIRouter(prefix="/capture/browser", tags=["browser-capture"])

# ── API key auth ──────────────────────────────────────────

_CAPTURE_API_KEY = os.environ.get("EG_CAPTURE_API_KEY", "")


async def _verify_api_key(x_eg_key: str = Header(default="", alias="X-EG-KEY")) -> None:
    """Require X-EG-KEY header to match EG_CAPTURE_API_KEY env var."""
    if not _CAPTURE_API_KEY:
        raise HTTPException(status_code=500, detail="EG_CAPTURE_API_KEY not configured on server")
    if x_eg_key != _CAPTURE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key (X-EG-KEY)")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ── Request / Response models ─────────────────────────────

class HighlightRequest(BaseModel):
    url: str
    title: str = ""
    highlight_text: str
    context: str = ""
    ts: str | None = None


class BookmarkRequest(BaseModel):
    url: str
    title: str = ""
    folder: str = ""
    ts: str | None = None


class TabInfo(BaseModel):
    url: str
    title: str = ""


class ResearchSessionRequest(BaseModel):
    session_title: str
    started_ts: str
    ended_ts: str
    tabs: list[TabInfo] = Field(default_factory=list)
    notes: str = ""


class VisitRequest(BaseModel):
    url: str
    title: str = ""
    ts: str | None = None
    duration_s: float | None = None


class ImportHistoryRequest(BaseModel):
    days: int = Field(default=7, ge=1, le=365)
    max_items: int = Field(default=500, ge=1, le=10000)
    entries: list[dict[str, Any]] = Field(default_factory=list)


class CaptureResponse(BaseModel):
    memory_id: str
    status: str = "ok"


class ImportHistoryResponse(BaseModel):
    imported: int
    memory_ids: list[str]
    status: str = "ok"


# ── Helpers ───────────────────────────────────────────────

def _create_browser_memory(
    card_type: str,
    summary: str,
    url: str,
    metadata: dict[str, Any],
    content_text: str = "",
    source_type: str = "browser",
) -> str:
    """Create SOURCE + MEMORY_CARD for a browser capture event."""
    source_id = upsert_source(url, source_type=source_type)
    memory_id = _new_id()

    meta = {
        "source_id": source_id,
        "url": url,
        "captured_ts": _now_iso(),
        "content_text": content_text[:5000] if content_text else None,
        **metadata,
    }

    db_repo.insert_memory_card(
        memory_id=memory_id,
        card_type=card_type,
        summary=summary[:500],
        metadata=meta,
    )

    # Enqueue text embedding job if we have substantial text
    if content_text and len(content_text.strip()) > 10:
        enqueue_job("ingest_capture", {
            "memory_id": memory_id,
            "text": content_text[:10000],
            "source_type": source_type,
            "card_type": card_type,
        })

    logger.info("Browser capture: %s — memory_id=%s url=%s", card_type, memory_id[:12], url[:60])
    return memory_id


# ── Endpoints ─────────────────────────────────────────────

@router.post("/highlight", response_model=CaptureResponse, dependencies=[Depends(_verify_api_key)])
async def capture_highlight(req: HighlightRequest):
    """Capture a text highlight from a web page."""
    summary = f"Highlight from {req.title or req.url}: {req.highlight_text[:200]}"
    memory_id = _create_browser_memory(
        card_type="browser_highlight",
        summary=summary,
        url=req.url,
        metadata={
            "title": req.title,
            "highlight_text": req.highlight_text,
            "context": req.context[:2000] if req.context else None,
            "ts": req.ts or _now_iso(),
        },
        content_text=req.highlight_text,
    )
    return CaptureResponse(memory_id=memory_id)


@router.post("/bookmark", response_model=CaptureResponse, dependencies=[Depends(_verify_api_key)])
async def capture_bookmark(req: BookmarkRequest):
    """Capture a bookmarked page."""
    summary = f"Bookmark: {req.title or req.url}"
    memory_id = _create_browser_memory(
        card_type="browser_bookmark",
        summary=summary,
        url=req.url,
        metadata={
            "title": req.title,
            "folder": req.folder or None,
            "ts": req.ts or _now_iso(),
        },
        content_text=f"{req.title}\n{req.url}",
    )
    return CaptureResponse(memory_id=memory_id)


@router.post("/research_session", response_model=CaptureResponse, dependencies=[Depends(_verify_api_key)])
async def capture_research_session(req: ResearchSessionRequest):
    """Capture a research session with multiple tabs and optional notes."""
    tab_summaries = "\n".join(f"- {t.title or t.url}" for t in req.tabs[:50])
    summary = f"Research session: {req.session_title} ({len(req.tabs)} tabs)"
    content_text = f"{req.session_title}\n\nTabs:\n{tab_summaries}"
    if req.notes:
        content_text += f"\n\nNotes:\n{req.notes}"

    # Use first tab URL or generate a synthetic URI
    url = req.tabs[0].url if req.tabs else f"session://{_new_id()}"

    memory_id = _create_browser_memory(
        card_type="browser_research",
        summary=summary,
        url=url,
        metadata={
            "session_title": req.session_title,
            "started_ts": req.started_ts,
            "ended_ts": req.ended_ts,
            "tabs": [t.model_dump() for t in req.tabs[:50]],
            "notes": req.notes[:2000] if req.notes else None,
        },
        content_text=content_text,
        source_type="browser_research",
    )
    return CaptureResponse(memory_id=memory_id)


@router.post("/visit", response_model=CaptureResponse, dependencies=[Depends(_verify_api_key)])
async def capture_visit(req: VisitRequest):
    """Capture a page visit (opt-in, controlled by allowlist).

    This endpoint is OFF by default — the browser extension must
    explicitly opt in and only send visits matching an allowlist.
    """
    summary = f"Visited: {req.title or req.url}"
    memory_id = _create_browser_memory(
        card_type="browser_visit",
        summary=summary,
        url=req.url,
        metadata={
            "title": req.title,
            "ts": req.ts or _now_iso(),
            "duration_s": req.duration_s,
        },
        content_text=f"{req.title}\n{req.url}",
    )
    return CaptureResponse(memory_id=memory_id)


@router.post("/import_history", response_model=ImportHistoryResponse, dependencies=[Depends(_verify_api_key)])
async def import_history(req: ImportHistoryRequest):
    """Import browsing history pushed by the browser extension.

    The server does NOT crawl — it only accepts data sent by the extension.
    Parameters control how much history the extension should push.
    """
    memory_ids: list[str] = []
    for entry in req.entries[:req.max_items]:
        url = entry.get("url", "")
        title = entry.get("title", "")
        ts = entry.get("ts", _now_iso())

        if not url:
            continue

        summary = f"History: {title or url}"
        memory_id = _create_browser_memory(
            card_type="browser_visit",
            summary=summary,
            url=url,
            metadata={
                "title": title,
                "ts": ts,
                "imported": True,
            },
            content_text=f"{title}\n{url}",
        )
        memory_ids.append(memory_id)

    return ImportHistoryResponse(
        imported=len(memory_ids),
        memory_ids=memory_ids,
    )
