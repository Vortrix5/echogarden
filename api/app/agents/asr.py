"""ASRAgent — stub that returns placeholder transcript."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class ASRAgent(BasePassiveAgent):
    name = "asr"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        audio_path = envelope.inputs.get("audio_path", "")
        return {"text": "(stub transcript)"}


registry.register(
    name="asr",
    version="0.1.0",
    description="Transcribe audio to text via ASR (stub).",
    input_schema={"type": "object", "properties": {"audio_path": {"type": "string"}}, "required": ["audio_path"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    agent_factory=ASRAgent,
)
