"""TextEmbedAgent — generates text embeddings via sentence-transformers + Qdrant."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class TextEmbedAgent(BasePassiveAgent):
    name = "text_embed"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.text_embed_impl import embed_text

        text = envelope.inputs.get("text", "")
        memory_id = envelope.inputs.get("memory_id", "")
        source_type = envelope.inputs.get("source_type", "file")
        return await embed_text(text, memory_id=memory_id, source_type=source_type)


registry.register(
    name="text_embed",
    version="0.2.0",
    description="Generate text embeddings via sentence-transformers and upsert to Qdrant.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "memory_id": {"type": "string"},
            "source_type": {"type": "string"},
        },
    },
    output_schema={"type": "object", "properties": {"vector_ref": {"type": "string"}}},
    agent_factory=TextEmbedAgent,
)
