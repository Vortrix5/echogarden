"""GraphBuilderAgent — build graph nodes/edges from pre-extracted entities.

Phase 6.1: Uses entity canonicalization and type normalization so that
semantically identical entities ("Dog", "dogs", " a dog ") converge to
a single graph node.
"""

from __future__ import annotations

import hashlib
import logging
import os

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
from app.graph.canonicalize import (
    canonicalize_entity_name,
    choose_display_name,
    normalize_entity_type,
)

logger = logging.getLogger("echogarden.agents.graph_builder")

_MAX_EDGES_PER_CARD = 30
_ABOUT_TYPES = {"Project", "Topic"}
_OLLAMA_MODEL = os.environ.get("EG_OLLAMA_MODEL", "phi3:mini")


def _entity_node_id(norm_type: str, canonical_name: str) -> str:
    """Deterministic node id from canonical type + name.

    >>> _entity_node_id("Topic", "dog")
    'ent:...'  # same hash every time for ("Topic", "dog")
    """
    raw = f"{norm_type}|{canonical_name}"
    h = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"ent:{h}"


def _edge_type_for(entity_type: str) -> str:
    """MENTIONS for Person/Org/Place, ABOUT for Project/Topic, MENTIONS for Other."""
    if entity_type in _ABOUT_TYPES:
        return "ABOUT"
    return "MENTIONS"


class GraphBuilderAgent(BasePassiveAgent):
    name = "graph_builder"
    version = "0.7.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        memory_id: str = envelope.inputs.get("memory_id", "")
        entities: list[dict] = envelope.inputs.get("entities", [])
        source: dict = envelope.inputs.get("source", {})
        call_id: str = envelope.inputs.get("_call_id", "")
        trace_id: str = envelope.trace_id

        nodes: list[dict] = []
        edges: list[dict] = []
        seen_ids: set[str] = set()

        for ent in entities[:_MAX_EDGES_PER_CARD]:
            raw_name = ent.get("name", "").strip()
            raw_type = ent.get("type", "Other")
            confidence = float(ent.get("confidence", 0.5))
            if not raw_name:
                continue

            # ── Canonicalize ──────────────────────────────
            norm_type = normalize_entity_type(raw_type)
            canon = canonicalize_entity_name(raw_name, entity_type=norm_type)
            if not canon:
                continue
            display = choose_display_name(raw_name, canon, norm_type)

            ent_id = _entity_node_id(norm_type, canon)

            logger.info(
                "[GRAPH] entity raw=%r type=%r -> canon=%r norm_type=%s node_id=%s",
                raw_name, raw_type, canon, norm_type, ent_id,
            )

            if ent_id not in seen_ids:
                seen_ids.add(ent_id)
                nodes.append({
                    "node_id": ent_id,
                    "node_type": norm_type,
                    "props": {
                        "name": display,
                        "canonical": canon,
                        "raw_name": raw_name,
                        "confidence": confidence,
                    },
                })

            # Always create edge — use placeholder mem node id;
            # orchestrator._upsert_graph() replaces it with real memory_id.
            mem_node_id = f"mem:{memory_id}" if memory_id else "mem:__placeholder__"
            edge_id = hashlib.sha1(
                f"{mem_node_id}|{_edge_type_for(norm_type)}|{ent_id}".encode()
            ).hexdigest()[:32]
            edges.append({
                "from_node_id": mem_node_id,
                "to_node_id": ent_id,
                "edge_type": _edge_type_for(norm_type),
                "weight": confidence,
                "edge_id": edge_id,
                "provenance": {
                    "created_by": "extractor",
                    "model": _OLLAMA_MODEL,
                    "trace_id": trace_id,
                    "tool": "graph_builder",
                    "tool_call_id": call_id,
                },
            })

        logger.info(
            "GraphBuilder: %d nodes, %d edges for memory=%s",
            len(nodes), len(edges), memory_id[:12] if memory_id else "?",
        )
        return {"nodes": nodes, "edges": edges}


registry.register(
    name="graph_builder",
    version="0.7.0",
    description="Build knowledge-graph nodes and edges from pre-extracted entities with canonicalization.",
    input_schema={
        "type": "object",
        "properties": {
            "memory_id": {"type": "string"},
            "entities": {"type": "array"},
            "source": {"type": "object"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "nodes": {"type": "array"},
            "edges": {"type": "array"},
        },
    },
    agent_factory=GraphBuilderAgent,
)
