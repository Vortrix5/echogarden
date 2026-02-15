"""OCRAgent — extracts text from images via Tesseract.

Returns structured output with status, error, and confidence fields.
Never returns error messages as text content.
"""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class OCRAgent(BasePassiveAgent):
    name = "ocr"
    version = "0.3.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.ocr_impl import extract_text

        image_path = envelope.inputs.get("image_path", "")
        return await extract_text(image_path)


registry.register(
    name="ocr",
    version="0.3.0",
    description="Extract text from images via Tesseract OCR. Returns structured output with status/confidence.",
    input_schema={
        "type": "object",
        "properties": {"image_path": {"type": "string"}},
        "required": ["image_path"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "status": {"type": "string"},
            "error": {"type": "string"},
            "avg_confidence": {"type": "number"},
        },
    },
    agent_factory=OCRAgent,
)
