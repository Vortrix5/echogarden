"""ASRAgent — stub that returns placeholder transcript."""

# from app.agents.base import BasePassiveAgent
# from app.core.tool_contracts import ToolEnvelope
from pathlib import Path
from typing import Dict, Any
import logging
from faster_whisper import WhisperModel
from app.core.tool_registry import registry


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class SpeechToTextProcessor:
    def __init__(self, model_size: str = "base", device: str = "cpu"):
        self.model = WhisperModel(model_size, device=device)
        self.model_size = model_size
        self.device = device
        logger.info(f"Initialized Whisper model: {model_size} on {device}")

    def process(self, file_path: str) -> Dict[str, Any]:
        file_path_obj = Path(file_path)

        if not file_path_obj.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")

        if not file_path_obj.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        segments, info = self.model.transcribe(str(file_path_obj))

        texts = []
        segment_list = []

        for segment in segments:
            texts.append(segment.text)
            segment_list.append(
                {
                    "id": segment.id,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
            )

        return {
            "status": "success",
            "language": info.language,
            "duration": info.duration,
            "text": " ".join(texts).strip(),
            "segments": segment_list,
            "origin": "speech_to_text",
        }


def transcribe_audio(
    file_path: str,
    model_size: str = "base",
    device: str = "cpu",
) -> Dict[str, Any]:
    processor = SpeechToTextProcessor(model_size=model_size, device=device)
    return processor.process(file_path)


class ASRAgent:
    def __init__(self, model_size: str = "base", device: str = "cpu"):
        self.processor = SpeechToTextProcessor(model_size=model_size, device=device)

    def execute(self, audio_path: str) -> Dict[str, Any]:
        return self.processor.process(audio_path)


registry.register(
    name="asr",
    version="1.0.0",
    description="Transcribe audio to text using Whisper ASR.",
    input_schema={
        "type": "object",
        "properties": {
            "audio_path": {"type": "string"}
        },
        "required": ["audio_path"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "status": {"type": "string"},
            "language": {"type": "string"},
            "duration": {"type": "number"},
            "text": {"type": "string"},
            "segments": {"type": "array"},
            "origin": {"type": "string"},
        },
    },
    agent_factory=lambda: ASRAgent(),
)
