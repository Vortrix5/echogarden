"""DocParseAgent — extracts text from documents via Apache Tika."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class DocParseAgent(BasePassiveAgent):
    name = "doc_parse"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.doc_parse_impl import parse_document

        text = envelope.inputs.get("text", "")
        path = envelope.inputs.get("path", "<inline>")
        blob_id = envelope.inputs.get("blob_id", "")

        # If text was pre-supplied (inline ingest) and no file path, return it directly
        if text and path == "<inline>":
            return {"content_text": text, "mime": "text/plain"}

        # Otherwise use Tika to parse the document
        result = await parse_document(path, blob_id)
        # If Tika returned empty but we had pre-read text, use that
        if not result.get("content_text") and text:
            result["content_text"] = text
        return result


registry.register(
    name="doc_parse",
    version="0.2.0",
    description="Parse documents (PDF/DOCX/PPTX/HTML/TXT) via Apache Tika.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "path": {"type": "string"},
            "blob_id": {"type": "string"},
        },
    },
    output_schema={"type": "object", "properties": {"content_text": {"type": "string"}, "mime": {"type": "string"}}},
    agent_factory=DocParseAgent,
)
