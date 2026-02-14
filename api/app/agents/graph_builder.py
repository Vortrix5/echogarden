"""GraphBuilderAgent — deterministic entity extraction for property graph."""

from __future__ import annotations

import re

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry

# Common English stopwords (capitalized forms) to exclude.
_STOPWORDS = frozenset({
    "THE", "AND", "BUT", "FOR", "NOR", "YET", "WITH", "FROM",
    "INTO", "UPON", "ABOUT", "AFTER", "BEFORE", "DURING", "THROUGH",
    "BETWEEN", "WITHOUT", "WITHIN", "ALONG", "AMONG", "ABOVE", "BELOW",
    "THIS", "THAT", "THESE", "THOSE", "WILL", "WOULD", "COULD", "SHOULD",
    "HAVE", "HAS", "HAD", "BEEN", "BEING", "ARE", "WAS", "WERE", "NOT",
    "ALL", "ANY", "EACH", "EVERY", "BOTH", "FEW", "MORE", "MOST", "OTHER",
    "SOME", "SUCH", "THAN", "TOO", "VERY", "CAN", "JUST", "DON", "NOW",
    "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "OUR", "OWN",
    "SAY", "SHE", "WHO", "WHY", "YOU", "DID", "GET", "GOT", "ONE",
    "TWO", "NEW", "OLD", "SEE", "WAY", "USE", "HER", "HIS", "ALSO",
})

_WORD_RE = re.compile(r"\b[A-Z][A-Za-z]{2,}\b")


def _extract_entities(text: str) -> list[str]:
    """Return sorted unique capitalised tokens (>=3 chars) not in stopwords."""
    tokens = _WORD_RE.findall(text)
    seen: set[str] = set()
    result: list[str] = []
    for t in tokens:
        key = t.upper()
        if key not in _STOPWORDS and key not in seen:
            seen.add(key)
            result.append(t)
    return sorted(result)


class GraphBuilderAgent(BasePassiveAgent):
    name = "graph_builder"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        content_text: str = envelope.inputs.get("content_text", "")
        memory_id: str = envelope.inputs.get("memory_id", "")
        call_id: str = envelope.inputs.get("_call_id", "")

        entities = _extract_entities(content_text)

        nodes: list[dict] = []
        edges: list[dict] = []

        for ent in entities:
            ent_id = f"ent:{ent.lower()}"
            nodes.append({
                "node_id": ent_id,
                "node_type": "Entity",
                "props": {"label": ent},
            })
            if memory_id:
                mem_node_id = f"mem:{memory_id}"
                edges.append({
                    "from_node_id": mem_node_id,
                    "to_node_id": ent_id,
                    "edge_type": "MENTIONS",
                    "weight": 1.0,
                    "provenance": {
                        "created_by": "GraphBuilderAgent",
                        "tool_call_id": call_id,
                        "confidence": 0.3,
                        "migrated": False,
                    },
                })

        return {"nodes": nodes, "edges": edges}


registry.register(
    name="graph_builder",
    version="0.1.0",
    description="Build knowledge-graph nodes and edges from content (stub).",
    input_schema={"type": "object", "properties": {"content_text": {"type": "string"}}},
    output_schema={
        "type": "object",
        "properties": {
            "nodes": {"type": "array"},
            "edges": {"type": "array"},
        },
    },
    agent_factory=GraphBuilderAgent,
)
