"""ASRAgent — stub that returns placeholder transcript."""

# from app.agents.base import BasePassiveAgent
# from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from faster_whisper import WhisperModel

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SpeechToTextProcessor:
    """
    Processes audio files using Whisper model for speech-to-text transcription.
    """
    
    def __init__(self, model_size: str = "base", device: str = "cpu"):
        """
        Initialize the speech-to-text processor.
        
        Args:
            model_size: Size of the Whisper model (e.g., "base", "small", "medium", "large")
            device: Device to run the model on ("cpu" or "cuda")
            
        Raises:
            RuntimeError: If model initialization fails
        """
        try:
            self.model = WhisperModel(model_size, device=device)
            self.model_size = model_size
            self.device = device
            logger.info(f"Initialized Whisper model: {model_size} on {device}")
        except Exception as e:
            logger.error(f"Failed to initialize Whisper model: {str(e)}")
            raise RuntimeError(f"Model initialization failed: {str(e)}")
    
    def process(self, file_path: str) -> Dict[str, Any]:
        """
        Process an audio file and extract transcription.
        
        Args:
            file_path: Path to the audio file
            
        Returns:
            Dictionary containing:
                - language: Detected language
                - duration: Audio duration in seconds
                - full_text: Complete transcription text
                - segments: List of transcribed segments with timing
                - status: Processing status
                
        Raises:
            FileNotFoundError: If the audio file does not exist
            Exception: If transcription fails
        """
        try:
            # Validate file path
            file_path_obj = Path(file_path)
            if not file_path_obj.exists():
                logger.error(f"Audio file not found: {file_path}")
                raise FileNotFoundError(f"Audio file not found: {file_path}")
            
            if not file_path_obj.is_file():
                logger.error(f"Path is not a file: {file_path}")
                raise ValueError(f"Path is not a file: {file_path}")
            
            logger.info(f"Starting transcription for: {file_path}")
            
            # Transcribe audio
            segments, info = self.model.transcribe(str(file_path_obj))
            
            # Process segments
            result_segments = []
            texts = []
            
            # Compile result
            result = {
                "status": "success",
                "language": info.language,
                "duration": info.duration,
                "full_text": " ".join(texts),
                "origin": "speech_to_text"
            }
            
            logger.info(f"Successfully transcribed audio. Duration: {info.duration}s, Language: {info.language}")
            return result
            
        except FileNotFoundError as e:
            logger.error(f"File error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "origin": "speech_to_text"
            }


# Module-level function for backward compatibility
def transcribe_audio(file_path: str, model_size: str = "base", device: str = "cpu") -> Dict[str, Any]:
    """
    Convenience function to transcribe an audio file.
    
    Args:
        file_path: Path to the audio file
        model_size: Size of the Whisper model
        device: Device to use for processing
        
    Returns:
        Dictionary containing transcription results
    """
    processor = SpeechToTextProcessor(model_size=model_size, device=device)
    return processor.process(file_path)


if __name__ == "__main__":
    # Example usage
    try:
        processor = SpeechToTextProcessor(model_size="base", device="cpu")
        result = processor.process(
            r"C:\Users\ilyes\Documents\github\ai_minds\Data Ingestion\SpeechToText\audio2.mp3"
        )
        print(json.dumps(result, indent=4, ensure_ascii=False))
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")


registry.register(
    name="asr",
    version="0.1.0",
    description="Transcribe audio to text via ASR (stub).",
    input_schema={"type": "object", "properties": {"audio_path": {"type": "string"}}, "required": ["audio_path"]},
    output_schema={"type": "object", "properties": {"text": {"type": "string"}}},
    agent_factory=ASRAgent,
)
