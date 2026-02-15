"""ImageCaptionAgent — generate a short caption for an image.

Uses BLIP model if available, otherwise falls back to heuristic caption
based on filename + image metadata. Never depends on OCR.
"""

from __future__ import annotations

import logging

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry

logger = logging.getLogger("echogarden.agents.image_caption")


class ImageCaptionAgent(BasePassiveAgent):
    name = "image_caption"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.image_caption_impl import generate_caption

        image_path = envelope.inputs.get("image_path", "")
        return await generate_caption(image_path)


registry.register(
    name="image_caption",
    version="0.1.0",
    description="Generate a short image caption (BLIP or heuristic fallback). Does not depend on OCR.",
    input_schema={
        "type": "object",
        "properties": {
            "image_path": {"type": "string"},
        },
        "required": ["image_path"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "caption": {"type": "string"},
            "model": {"type": "string"},
            "status": {"type": "string"},
        },
    },
    agent_factory=ImageCaptionAgent,
)
