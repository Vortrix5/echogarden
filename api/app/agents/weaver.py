"""WeaverAgent — stub that returns a placeholder answer."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class WeaverAgent(BasePassiveAgent):
    name = "weaver"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        return {"answer": "(stub answer)", "citations": []}


registry.register(
    name="weaver",
    version="0.1.0",
    description="Weave retrieved context into a coherent answer (stub).",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "context": {"type": "array"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {"type": "array"},
        },
    },
    agent_factory=WeaverAgent,
)
