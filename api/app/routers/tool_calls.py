"""Router: GET /tool_calls — list tool call records."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from app.db import repo

router = APIRouter(tags=["tool_calls"])


@router.get("/tool_calls")
async def list_tool_calls(
    trace_id: str | None = Query(default=None, description="Filter by trace_id"),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Return tool_call rows, optionally filtered by trace_id."""
    if trace_id:
        return repo.get_tool_calls_for_trace(trace_id, limit=limit)
    return repo.get_recent_tool_calls(limit=limit)
