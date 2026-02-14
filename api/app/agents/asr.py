"""ASRAgent — transcribes audio via faster-whisper."""

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry


class ASRAgent(BasePassiveAgent):
    name = "asr"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        from app.tools.asr_impl import transcribe

        audio_path = envelope.inputs.get("audio_path", "")
        return await transcribe(audio_path)


registry.register(
    name="asr",
    version="0.2.0",
    description="Transcribe audio to text via faster-whisper.",
    input_schema={"type": "object", "properties": {"audio_path": {"type": "string"}}, "required": ["audio_path"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    agent_factory=ASRAgent,
)
