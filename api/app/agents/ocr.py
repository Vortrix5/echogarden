"""OCRAgent — stub that returns placeholder OCR text."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class OCRAgent(BasePassiveAgent):
    name = "ocr"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        image_path = envelope.inputs.get("image_path", "")
        return {"text": "(stub ocr)"}


registry.register(
    name="ocr",
    version="0.1.0",
    description="Extract text from an image via OCR (stub).",
    input_schema={"type": "object", "properties": {"image_path": {"type": "string"}}, "required": ["image_path"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    agent_factory=OCRAgent,
)
