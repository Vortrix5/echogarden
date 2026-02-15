"""Phase 5 — Pydantic request / response models for hybrid retrieval."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=8, ge=1, le=200)
    time_min: str | None = None  # ISO-8601 or null
    time_max: str | None = None
    source_types: list[str] | None = None  # e.g. ["file_capture","browser_highlight"]
    use_semantic: bool = True
    use_graph: bool = True
    hops: int = Field(default=1, ge=0, le=2)
    fts_k: int = Field(default=50, ge=1, le=500)
    vec_k: int = Field(default=50, ge=1, le=500)
    seed_k: int = Field(default=10, ge=1, le=100)


class SignalBreakdown(BaseModel):
    fts: float = 0.0
    semantic: float = 0.0
    graph: float = 0.0
    recency: float = 0.0
    source_boost: float = 0.0


class GraphPath(BaseModel):
    via_entity_ids: list[str] = Field(default_factory=list)


class RetrievedCard(BaseModel):
    memory_id: str
    summary: str | None = None
    created_at: str | None = None
    source_type: str | None = None
    final_score: float = 0.0
    signals: SignalBreakdown = Field(default_factory=SignalBreakdown)
    reasons: list[str] = Field(default_factory=list)
    graph_path: GraphPath | None = None
    # Phase 9 — media-first fields
    title: str | None = None
    mime: str | None = None
    media_url: str | None = None
    thumb_url: str | None = None
    open_url: str | None = None


class RetrieveResponse(BaseModel):
    results: list[RetrievedCard] = Field(default_factory=list)
