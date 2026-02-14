"""OCRAgent — extracts text from images via Tesseract."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class OCRAgent(BasePassiveAgent):
    name = "ocr"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.ocr_impl import extract_text

        image_path = envelope.inputs.get("image_path", "")
        return await extract_text(image_path)


registry.register(
    name="ocr",
    version="0.2.0",
    description="Extract text from images via Tesseract OCR.",
    input_schema={"type": "object", "properties": {"image_path": {"type": "string"}}, "required": ["image_path"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    agent_factory=OCRAgent,
)
