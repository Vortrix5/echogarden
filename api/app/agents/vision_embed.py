"""VisionEmbedAgent — stub that returns a deterministic vector reference."""

import hashlib

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class VisionEmbedAgent(BasePassiveAgent):
    name = "vision_embed"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        raw = str(envelope.inputs)
        h = hashlib.sha256(raw.encode()).hexdigest()[:12]
        return {"vector_ref": f"qdrant:stub:vision:{h}"}


registry.register(
    name="vision_embed",
    version="0.1.0",
    description="Generate a vision embedding vector reference (stub).",
    input_schema={"type": "object", "properties": {"image_path": {"type": "string"}}},
    output_schema={"type": "object", "properties": {"vector_ref": {"type": "string"}}},
    agent_factory=VisionEmbedAgent,
)
