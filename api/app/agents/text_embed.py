"""TextEmbedAgent — stub that returns a deterministic vector reference."""

import hashlib

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class TextEmbedAgent(BasePassiveAgent):
    name = "text_embed"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        raw = str(envelope.inputs)
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return {"vector_ref": f"qdrant:stub:text:{h}"}


registry.register(
    name="text_embed",
    version="0.1.0",
    description="Generate a text embedding vector reference (stub).",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"vector_ref": {"type": "string"}}},
    agent_factory=TextEmbedAgent,
)
