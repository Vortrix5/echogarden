"""RetrievalAgent — real FTS-based retrieval against memory_card."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
from app.db.repo import fts_search_memory_cards


class RetrievalAgent(BasePassiveAgent):
    name = "retrieval"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        query = envelope.inputs.get("query", "")
        limit = envelope.inputs.get("limit", 10)
        results = fts_search_memory_cards(query, limit=limit)
        return {"results": results}


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
