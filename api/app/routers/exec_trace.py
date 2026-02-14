"""Router: GET /exec/{trace_id} — inspect execution traces."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from app.db import repo

router = APIRouter(tags=["exec"])


@router.get("/exec/{trace_id}")
async def get_exec_trace(trace_id: str) -> dict[str, Any]:
    """Return the execution trace, its nodes, and edges."""
    trace = repo.get_exec_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")

    nodes = repo.get_exec_nodes_for_trace(trace_id)
    edges = repo.get_exec_edges_for_trace(trace_id)

    # Parse metadata_json
    meta = trace.get("metadata_json")
    if meta and isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except json.JSONDecodeError:
            pass

    return {
        "trace_id": trace["trace_id"],
        "started_ts": trace.get("started_ts"),
        "finished_ts": trace.get("finished_ts"),
        "status": trace.get("status"),
        "metadata": meta,
        "nodes": nodes,
        "edges": edges,
    }
