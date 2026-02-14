"""Pydantic request/response models for the Graph Service."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Node / Edge inputs ───────────────────────────────────
class GraphNodeIn(BaseModel):
    node_id: str
    node_type: str = "Entity"
    props: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeIn(BaseModel):
    edge_id: str | None = None  # auto-generated if missing
    from_node_id: str
    to_node_id: str
    edge_type: str = "RELATED"
    weight: float = 1.0
    valid_from: str | None = None
    valid_to: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


# ── Upsert ────────────────────────────────────────────────
class UpsertRequest(BaseModel):
    nodes: list[GraphNodeIn] = Field(default_factory=list)
    edges: list[GraphEdgeIn] = Field(default_factory=list)


class UpsertResponse(BaseModel):
    nodes_upserted: int = 0
    edges_upserted: int = 0
    ok: bool = True


# ── Query (neighbors) ────────────────────────────────────
class QueryRequest(BaseModel):
    node_id: str
    direction: str = Field(default="both", pattern="^(out|in|both)$")
    edge_types: list[str] | None = None
    time_min: str | None = None
    time_max: str | None = None
    limit: int = Field(default=50, ge=1, le=500)


class GraphNodeOut(BaseModel):
    node_id: str
    node_type: str | None = None
    created_at: str | None = None
    props: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeOut(BaseModel):
    edge_id: str
    from_node_id: str
    to_node_id: str
    edge_type: str | None = None
    weight: float = 1.0
    valid_from: str | None = None
    valid_to: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    node: GraphNodeOut | None = None
    neighbors: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)


# ── Expand (BFS) ─────────────────────────────────────────
class ExpandRequest(BaseModel):
    seed_node_ids: list[str]
    hops: int = Field(default=1, ge=1, le=2)
    direction: str = Field(default="both", pattern="^(out|in|both)$")
    edge_types: list[str] | None = None
    time_min: str | None = None
    time_max: str | None = None
    max_nodes: int = Field(default=300, ge=1, le=1000)
    max_edges: int = Field(default=1000, ge=1, le=5000)


class PathInfo(BaseModel):
    target_node_id: str
    via_edge_ids: list[str] = Field(default_factory=list)


class ExpandResponse(BaseModel):
    nodes: list[GraphNodeOut] = Field(default_factory=list)
    edges: list[GraphEdgeOut] = Field(default_factory=list)
    paths: list[PathInfo] = Field(default_factory=list)
