"""RetrievalAgent — FTS search + graph-expand enrichment."""

from __future__ import annotations

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
from app.db.repo import fts_search_memory_cards
from app.graph.service import GraphService

_graph = GraphService()

_EXPAND_EDGE_TYPES = ["MENTIONS", "ABOUT", "FOLLOWS", "SUPPORTS"]
_MAX_GRAPH_ADDITIONS = 20


class RetrievalAgent(BasePassiveAgent):
    name = "retrieval"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        query = envelope.inputs.get("query", "")
        limit = envelope.inputs.get("limit", 10)
        hops = envelope.inputs.get("hops", 1)

        # ── Step 1: FTS search ────────────────────────────
        fts_results = fts_search_memory_cards(query, limit=limit)
        fts_ids = {r["memory_id"] for r in fts_results}

        # Tag each FTS result with reason
        for r in fts_results:
            r["reason"] = "fts"

        # ── Step 2: Graph expand from FTS hits ────────────
        graph_additions: list[dict] = []
        if fts_ids:
            seed_node_ids = [f"mem:{mid}" for mid in fts_ids]
            try:
                expansion = _graph.expand(
                    seed_node_ids=seed_node_ids,
                    hops=hops,
                    direction="both",
                    edge_types=_EXPAND_EDGE_TYPES,
                    max_nodes=300,
                    max_edges=1000,
                )
                # Collect MemoryCard nodes not already in FTS results
                path_map = {p.target_node_id: p.via_edge_ids for p in expansion.paths}
                for node in expansion.nodes:
                    if node.node_type == "MemoryCard":
                        # Extract bare memory_id from "mem:<id>"
                        bare_id = node.node_id
                        if bare_id.startswith("mem:"):
                            bare_id = bare_id[4:]
                        if bare_id not in fts_ids:
                            graph_additions.append({
                                "memory_id": bare_id,
                                "summary": node.props.get("summary", ""),
                                "score": 0.0,
                                "reason": "graph_expand",
                                "path_edge_ids": path_map.get(node.node_id, []),
                            })
                            if len(graph_additions) >= _MAX_GRAPH_ADDITIONS:
                                break
            except Exception:
                # Graph expand is best-effort; don't fail retrieval
                pass

        return {"results": fts_results + graph_additions}


registry.register(
    name="retrieval",
    version="0.1.0",
    description="Full-text search over memory cards (real FTS5).",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "score": {"type": "number"},
                    },
                },
            }
        },
    },
    agent_factory=RetrievalAgent,
)
