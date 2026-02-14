"""Router: Ingest stub orchestrator."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.tool_contracts import ToolEnvelope, ToolResult
from app.core.tool_registry import registry
from app.db.repo import insert_memory_card
from app.graph.models import GraphEdgeIn, GraphNodeIn
from app.graph.service import GraphService

router = APIRouter(tags=["ingest"])
_graph = GraphService()


class IngestRequest(BaseModel):
    text: str


class IngestResponse(BaseModel):
    memory_id: str
    trace_id: str
    steps: list[ToolResult]


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    """Minimal ingest orchestrator: DocParse -> TextEmbed -> GraphBuilder.

    Creates a MEMORY_CARD, then creates graph nodes/edges and returns the
    memory_id + trace.
    """
    trace_id = uuid.uuid4().hex
    steps: list[ToolResult] = []

    # ── Step 1: DocParse ──────────────────────────────────
    doc_parse = registry.get("doc_parse")
    agent1 = doc_parse.agent_factory()
    env1 = ToolEnvelope(
        trace_id=trace_id,
        callee="doc_parse",
        intent="ingest.parse",
        inputs={"text": req.text},
    )
    r1 = await agent1.run(env1)
    steps.append(r1)
    content_text = r1.outputs.get("content_text", req.text)

    # ── Step 2: TextEmbed ─────────────────────────────────
    text_embed = registry.get("text_embed")
    agent2 = text_embed.agent_factory()
    env2 = ToolEnvelope(
        trace_id=trace_id,
        callee="text_embed",
        intent="ingest.embed",
        inputs={"text": content_text},
    )
    r2 = await agent2.run(env2)
    steps.append(r2)

    # ── Persist memory card ───────────────────────────────
    memory_id = uuid.uuid4().hex
    summary = content_text[:200]
    insert_memory_card(
        memory_id=memory_id,
        card_type="note",
        summary=summary,
        metadata={"content_text": content_text},
    )

    # ── Step 3: GraphBuilder — extract entities ───────────
    graph_builder = registry.get("graph_builder")
    agent3 = graph_builder.agent_factory()
    gb_call_id = uuid.uuid4().hex
    env3 = ToolEnvelope(
        trace_id=trace_id,
        callee="graph_builder",
        intent="ingest.graph",
        inputs={
            "content_text": content_text,
            "memory_id": memory_id,
            "_call_id": gb_call_id,
        },
    )
    r3 = await agent3.run(env3)
    steps.append(r3)

    # ── Step 4: Upsert graph nodes + edges ────────────────
    # Always create the MemoryCard node
    mem_node = GraphNodeIn(
        node_id=f"mem:{memory_id}",
        node_type="MemoryCard",
        props={"summary": summary},
    )
    entity_nodes = [GraphNodeIn(**n) for n in r3.outputs.get("nodes", [])]
    _graph.upsert_nodes([mem_node] + entity_nodes)

    raw_edges = r3.outputs.get("edges", [])
    graph_edges: list[GraphEdgeIn] = []
    for e in raw_edges:
        # Inject tool_call_id into provenance if not present
        prov = e.get("provenance", {})
        if not prov.get("tool_call_id"):
            prov["tool_call_id"] = gb_call_id
        graph_edges.append(GraphEdgeIn(**{**e, "provenance": prov}))
    _graph.upsert_edges(graph_edges)

    return IngestResponse(memory_id=memory_id, trace_id=trace_id, steps=steps)
