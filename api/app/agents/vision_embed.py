"""VisionEmbedAgent — generates image embeddings via OpenCLIP + Qdrant."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class VisionEmbedAgent(BasePassiveAgent):
    name = "vision_embed"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.vision_embed_impl import embed_image

        image_path = envelope.inputs.get("image_path", "")
        blob_id = envelope.inputs.get("blob_id", "")
        memory_id = envelope.inputs.get("memory_id", "")
        mime = envelope.inputs.get("mime", "")
        return await embed_image(image_path, blob_id=blob_id, memory_id=memory_id, mime=mime)


registry.register(
    name="vision_embed",
    version="0.2.0",
    description="Generate image embeddings via OpenCLIP and upsert to Qdrant.",
    input_schema={
        "type": "object",
        "properties": {
            "image_path": {"type": "string"},
            "blob_id": {"type": "string"},
            "memory_id": {"type": "string"},
            "mime": {"type": "string"},
        },
    },
    output_schema={"type": "object", "properties": {"vector_ref": {"type": "string"}}},
    agent_factory=VisionEmbedAgent,
)
