"""DocParseAgent — stub that echoes text input as parsed content."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class DocParseAgent(BasePassiveAgent):
    name = "doc_parse"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        text = envelope.inputs.get("text", "")
        return {"content_text": text, "mime": "text/plain"}


registry.register(
    name="doc_parse",
    version="0.1.0",
    description="Parse a document and extract structured content (stub).",
    input_schema={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    output_schema={"type": "object", "properties": {"content_text": {"type": "string"}, "mime": {"type": "string"}}},
    agent_factory=DocParseAgent,
)
