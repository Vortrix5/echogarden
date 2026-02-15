"""Phase 8 — Graph UI endpoints for subgraph visualization."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Query

from app.db.conn import get_conn
from app.graph.service import GraphService

logger = logging.getLogger("echogarden.routers.graph_ui")
router = APIRouter(prefix="/graph", tags=["graph-ui"])
_svc = GraphService()


# ── Shared UI-friendly node/edge format ──────────────────

def _ui_node(row) -> dict:
    """Convert a graph_node row to the UI format with short labels."""
    props = row["props"]
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except (json.JSONDecodeError, TypeError):
            props = {}
    props = props or {}
    node_type = row["node_type"] or "Entity"

    if node_type == "MemoryCard":
        label = (props.get("summary") or props.get("name") or row["node_id"])[:60]
    else:
        label = (props.get("name") or props.get("canonical") or row["node_id"])[:40]

    return {
        "id": row["node_id"],
        "type": node_type,
        "label": label,
        "props": props,
    }


def _ui_edge(row) -> dict:
    prov = row["provenance"]
    if isinstance(prov, str):
        try:
            prov = json.loads(prov)
        except (json.JSONDecodeError, TypeError):
            prov = {}
    return {
        "id": row["edge_id"],
        "source": row["from_node_id"],
        "target": row["to_node_id"],
        "type": row["edge_type"] or "RELATED",
        "weight": row["weight"],
    }


# ── GET /graph/subgraph ──────────────────────────────────

@router.get("/subgraph")
async def subgraph(
    seed: str = Query(..., description="Node ID to seed from (e.g. mem:xxx or ent:xxx)"),
    hops: int = Query(1, ge=1, le=2),
    limit: int = Query(200, ge=10, le=500),
):
    """Return a subgraph seeded from a node, up to N hops."""
    conn = get_conn()
    try:
        # BFS expand
        visited: set[str] = {seed}
        frontier = [seed]
        all_edge_rows = []

        for _ in range(hops):
            if not frontier:
                break
            ph = ",".join("?" for _ in frontier)
            edge_rows = conn.execute(
                f"""SELECT edge_id, from_node_id, to_node_id, edge_type, weight, provenance
                    FROM graph_edge
                    WHERE from_node_id IN ({ph}) OR to_node_id IN ({ph})
                    LIMIT ?""",
                [*frontier, *frontier, limit - len(all_edge_rows)],
            ).fetchall()

            next_frontier = []
            for r in edge_rows:
                all_edge_rows.append(r)
                for nid in (r["from_node_id"], r["to_node_id"]):
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.append(nid)
                if len(visited) >= limit:
                    break
            frontier = next_frontier

        # Fetch node details
        node_ids = list(visited)
        nodes = _fetch_ui_nodes(conn, node_ids)
        edges = [_ui_edge(r) for r in all_edge_rows]

        return {"nodes": nodes, "edges": edges}
    finally:
        conn.close()


# ── GET /graph/search ────────────────────────────────────

@router.get("/search")
async def graph_search(
    query: str = Query(..., min_length=1),
    type: str | None = Query(None, alias="type"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search graph nodes by name/canonical/summary text (LIKE match)."""
    conn = get_conn()
    try:
        clauses = [
            """(json_extract(props, '$.name') LIKE ?
               OR json_extract(props, '$.canonical') LIKE ?
               OR json_extract(props, '$.summary') LIKE ?
               OR node_id LIKE ?)"""
        ]
        params: list[Any] = [f"%{query}%"] * 4

        if type:
            clauses.append("node_type = ?")
            params.append(type)

        where = " AND ".join(clauses)
        params.append(limit)

        rows = conn.execute(
            f"""SELECT node_id, node_type, created_at, props
                FROM graph_node
                WHERE {where}
                ORDER BY created_at DESC
                LIMIT ?""",
            params,
        ).fetchall()

        return {"nodes": [_ui_node(r) for r in rows]}
    finally:
        conn.close()


# ── GET /graph/neighbors ─────────────────────────────────

@router.get("/neighbors")
async def graph_neighbors(
    node_id: str = Query(...),
    hops: int = Query(1, ge=1, le=2),
    limit: int = Query(200, ge=10, le=500),
):
    """Return neighbors of a node — same as subgraph but explicit naming."""
    conn = get_conn()
    try:
        visited: set[str] = {node_id}
        frontier = [node_id]
        all_edge_rows = []

        for _ in range(hops):
            if not frontier:
                break
            ph = ",".join("?" for _ in frontier)
            edge_rows = conn.execute(
                f"""SELECT edge_id, from_node_id, to_node_id, edge_type, weight, provenance
                    FROM graph_edge
                    WHERE from_node_id IN ({ph}) OR to_node_id IN ({ph})
                    LIMIT ?""",
                [*frontier, *frontier, limit - len(all_edge_rows)],
            ).fetchall()

            next_frontier = []
            for r in edge_rows:
                all_edge_rows.append(r)
                for nid in (r["from_node_id"], r["to_node_id"]):
                    if nid not in visited:
                        visited.add(nid)
                        next_frontier.append(nid)
                if len(visited) >= limit:
                    break
            frontier = next_frontier

        nodes = _fetch_ui_nodes(conn, list(visited))
        edges = [_ui_edge(r) for r in all_edge_rows]

        return {"nodes": nodes, "edges": edges}
    finally:
        conn.close()


# ── helpers ──────────────────────────────────────────────

def _fetch_ui_nodes(conn, node_ids: list[str]) -> list[dict]:
    if not node_ids:
        return []
    ph = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"""SELECT node_id, node_type, created_at, props
            FROM graph_node WHERE node_id IN ({ph})""",
        node_ids,
    ).fetchall()
    return [_ui_node(r) for r in rows]
