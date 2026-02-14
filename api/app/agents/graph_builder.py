"""GraphBuilderAgent — stub that returns empty nodes/edges."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class GraphBuilderAgent(BasePassiveAgent):
    name = "graph_builder"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        return {"nodes": [], "edges": []}


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
