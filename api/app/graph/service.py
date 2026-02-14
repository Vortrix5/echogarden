"""GraphService — SQLite property-graph with upsert, neighbors, and BFS expand."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict, deque
from typing import Any

from app.db.conn import get_conn
from app.graph.models import (
    ExpandResponse,
    GraphEdgeIn,
    GraphEdgeOut,
    GraphNodeIn,
    GraphNodeOut,
    PathInfo,
    QueryResponse,
)


def _make_edge_id(edge: GraphEdgeIn) -> str:
    """Deterministic edge_id from (from, type, to, valid_from, valid_to)."""
    raw = "|".join([
        edge.from_node_id,
        edge.edge_type,
        edge.to_node_id,
        edge.valid_from or "",
        edge.valid_to or "",
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class GraphService:
    """Stateless service — each call opens its own connection."""

    # ── upsert ────────────────────────────────────────────
    def upsert_nodes(self, nodes: list[GraphNodeIn]) -> int:
        if not nodes:
            return 0
        conn = get_conn()
        try:
            for n in nodes:
                conn.execute(
                    """INSERT INTO graph_node (node_id, node_type, props)
                       VALUES (?, ?, ?)
                       ON CONFLICT(node_id) DO UPDATE SET
                         node_type = excluded.node_type,
                         props     = excluded.props""",
                    (n.node_id, n.node_type, json.dumps(n.props)),
                )
            conn.commit()
            return len(nodes)
        finally:
            conn.close()

    def upsert_edges(self, edges: list[GraphEdgeIn]) -> int:
        if not edges:
            return 0
        conn = get_conn()
        try:
            for e in edges:
                eid = e.edge_id or _make_edge_id(e)
                conn.execute(
                    """INSERT INTO graph_edge
                         (edge_id, from_node_id, to_node_id, edge_type,
                          weight, valid_from, valid_to, provenance)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(edge_id) DO UPDATE SET
                         edge_type  = excluded.edge_type,
                         weight     = excluded.weight,
                         valid_from = excluded.valid_from,
                         valid_to   = excluded.valid_to,
                         provenance = excluded.provenance""",
                    (
                        eid,
                        e.from_node_id,
                        e.to_node_id,
                        e.edge_type,
                        e.weight,
                        e.valid_from,
                        e.valid_to,
                        json.dumps(e.provenance),
                    ),
                )
            conn.commit()
            return len(edges)
        finally:
            conn.close()

    # ── single-node lookup ────────────────────────────────
    def get_node(self, node_id: str) -> GraphNodeOut | None:
        conn = get_conn()
        try:
            row = conn.execute(
                "SELECT node_id, node_type, created_at, props FROM graph_node WHERE node_id = ?",
                (node_id,),
            ).fetchone()
            if row is None:
                return None
            return _row_to_node(row)
        finally:
            conn.close()

    # ── neighbors (1-hop) ─────────────────────────────────
    def neighbors(
        self,
        node_id: str,
        direction: str = "both",
        edge_types: list[str] | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        limit: int = 50,
    ) -> QueryResponse:
        center = self.get_node(node_id)
        conn = get_conn()
        try:
            edge_rows = _fetch_edges(
                conn,
                node_ids=[node_id],
                direction=direction,
                edge_types=edge_types,
                time_min=time_min,
                time_max=time_max,
                limit=limit,
            )
            edges = [_row_to_edge(r) for r in edge_rows]
            neighbor_ids = set()
            for e in edges:
                if e.from_node_id != node_id:
                    neighbor_ids.add(e.from_node_id)
                if e.to_node_id != node_id:
                    neighbor_ids.add(e.to_node_id)
            neighbors = _fetch_nodes(conn, list(neighbor_ids))
            return QueryResponse(node=center, neighbors=neighbors, edges=edges)
        finally:
            conn.close()

    # ── expand (bounded BFS) ──────────────────────────────
    def expand(
        self,
        seed_node_ids: list[str],
        hops: int = 1,
        direction: str = "both",
        edge_types: list[str] | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
        max_nodes: int = 300,
        max_edges: int = 1000,
    ) -> ExpandResponse:
        visited_nodes: set[str] = set(seed_node_ids)
        collected_edges: list[GraphEdgeOut] = []
        # paths: target -> list of edge_ids leading to it
        paths: dict[str, list[str]] = defaultdict(list)

        frontier = deque(seed_node_ids)
        conn = get_conn()
        try:
            for _hop in range(hops):
                next_frontier: list[str] = []
                if not frontier:
                    break

                batch_ids = list(frontier)
                frontier.clear()

                edge_rows = _fetch_edges(
                    conn,
                    node_ids=batch_ids,
                    direction=direction,
                    edge_types=edge_types,
                    time_min=time_min,
                    time_max=time_max,
                    limit=max_edges - len(collected_edges),
                )

                for r in edge_rows:
                    if len(collected_edges) >= max_edges:
                        break
                    edge = _row_to_edge(r)
                    collected_edges.append(edge)

                    # Determine which end is the "other" node
                    other = (
                        edge.to_node_id
                        if edge.from_node_id in visited_nodes
                        else edge.from_node_id
                    )
                    # Build path: extend parent's path
                    parent = (
                        edge.from_node_id
                        if edge.from_node_id in visited_nodes
                        else edge.to_node_id
                    )
                    if other not in visited_nodes:
                        visited_nodes.add(other)
                        next_frontier.append(other)
                        paths[other] = paths.get(parent, []) + [edge.edge_id]
                        if len(visited_nodes) >= max_nodes:
                            break
                    else:
                        # Still record the edge path if shorter/new
                        if other not in paths:
                            paths[other] = paths.get(parent, []) + [edge.edge_id]

                frontier.extend(next_frontier)

            all_node_ids = list(visited_nodes)
            nodes = _fetch_nodes(conn, all_node_ids)
            path_infos = [
                PathInfo(target_node_id=tid, via_edge_ids=eids)
                for tid, eids in paths.items()
            ]
            return ExpandResponse(nodes=nodes, edges=collected_edges, paths=path_infos)
        finally:
            conn.close()


# ── internal helpers ──────────────────────────────────────

def _row_to_node(row) -> GraphNodeOut:
    props = row["props"]
    if isinstance(props, str):
        props = json.loads(props)
    return GraphNodeOut(
        node_id=row["node_id"],
        node_type=row["node_type"],
        created_at=row["created_at"],
        props=props or {},
    )


def _row_to_edge(row) -> GraphEdgeOut:
    prov = row["provenance"]
    if isinstance(prov, str):
        prov = json.loads(prov)
    return GraphEdgeOut(
        edge_id=row["edge_id"],
        from_node_id=row["from_node_id"],
        to_node_id=row["to_node_id"],
        edge_type=row["edge_type"],
        weight=row["weight"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
        provenance=prov or {},
    )


def _fetch_nodes(conn, node_ids: list[str]) -> list[GraphNodeOut]:
    if not node_ids:
        return []
    placeholders = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"SELECT node_id, node_type, created_at, props FROM graph_node WHERE node_id IN ({placeholders})",
        node_ids,
    ).fetchall()
    return [_row_to_node(r) for r in rows]


def _fetch_edges(
    conn,
    node_ids: list[str],
    direction: str = "both",
    edge_types: list[str] | None = None,
    time_min: str | None = None,
    time_max: str | None = None,
    limit: int = 500,
) -> list[Any]:
    """Fetch edges touching *node_ids* with optional filters."""
    placeholders = ",".join("?" for _ in node_ids)
    params: list[Any] = []

    # Direction clause
    if direction == "out":
        dir_clause = f"from_node_id IN ({placeholders})"
        params.extend(node_ids)
    elif direction == "in":
        dir_clause = f"to_node_id IN ({placeholders})"
        params.extend(node_ids)
    else:
        dir_clause = f"(from_node_id IN ({placeholders}) OR to_node_id IN ({placeholders}))"
        params.extend(node_ids)
        params.extend(node_ids)

    filters = [dir_clause]

    # Edge type filter
    if edge_types:
        et_ph = ",".join("?" for _ in edge_types)
        filters.append(f"edge_type IN ({et_ph})")
        params.extend(edge_types)

    # Time validity filter (edges without valid_from/valid_to are always valid)
    if time_min:
        filters.append("(valid_to IS NULL OR valid_to >= ?)")
        params.append(time_min)
    if time_max:
        filters.append("(valid_from IS NULL OR valid_from <= ?)")
        params.append(time_max)

    where = " AND ".join(filters)
    params.append(limit)

    return conn.execute(
        f"""SELECT edge_id, from_node_id, to_node_id, edge_type,
                   weight, valid_from, valid_to, provenance
            FROM graph_edge
            WHERE {where}
            LIMIT ?""",
        params,
    ).fetchall()
