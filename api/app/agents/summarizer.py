"""SummarizerAgent — produce short (1-3 sentence) summaries via local LLM."""

from __future__ import annotations

import logging

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
from app.llm.ollama_client import (
    LLMUnavailableError,
    llm_available,
    ollama_generate,
)
from app.llm.prompts import summarizer_prompt

logger = logging.getLogger("echogarden.agents.summarizer")

_MAX_SUMMARY_CHARS = 400


def _fallback_summary(content_text: str, max_chars: int = _MAX_SUMMARY_CHARS) -> str:
    """Produce a truncated first-sentence fallback when LLM is unavailable."""
    text = content_text.strip()
    if not text:
        return "(empty document)"
    # Take first sentence(s) up to max_chars
    # Try to break at sentence boundary
    cut = text[:max_chars]
    for sep in (". ", ".\n", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > 40:
            return cut[: idx + 1].strip()
    # No sentence boundary found — hard truncate
    if len(text) > max_chars:
        return cut[:max_chars - 3].rstrip() + "..."
    return cut.strip()


class SummarizerAgent(BasePassiveAgent):
    name = "summarizer"
    version = "0.6.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        content_text: str = envelope.inputs.get("content_text", "")
        title: str | None = envelope.inputs.get("title")
        max_chars: int = envelope.inputs.get("max_chars", _MAX_SUMMARY_CHARS)

        if not content_text.strip():
            return {"summary": "(empty document)"}

        # Attempt LLM summarization
        try:
            if not await llm_available():
                raise LLMUnavailableError("LLM not available")

            prompt = summarizer_prompt(content_text, title, max_chars)
            raw = await ollama_generate(
                prompt, timeout=60.0, num_predict=256,
            )
            summary = raw.strip()

            # Hard cap
            if len(summary) > max_chars:
                # Try graceful truncate at sentence boundary
                cut = summary[:max_chars]
                for sep in (". ", ".\n"):
                    idx = cut.rfind(sep)
                    if idx > 40:
                        summary = cut[: idx + 1].strip()
                        break
                else:
                    summary = cut[:max_chars - 3].rstrip() + "..."

            # Safety: ensure summary != content_text
            if summary == content_text[:len(summary)]:
                summary = _fallback_summary(content_text, max_chars)

            logger.info("LLM summary produced (%d chars)", len(summary))
            return {"summary": summary, "llm_used": True}

        except (LLMUnavailableError, Exception) as exc:
            logger.info("LLM failed (%s) — using fallback summary", type(exc).__name__)
            summary = _fallback_summary(content_text, max_chars)
            return {"summary": summary, "llm_used": False}


registry.register(
    name="summarizer",
    version="0.6.0",
    description="Produce a short 1-3 sentence summary via local LLM (Phi-3 mini). Fallback if LLM unavailable.",
    input_schema={
        "type": "object",
        "properties": {
            "content_text": {"type": "string"},
            "title": {"type": ["string", "null"]},
            "max_chars": {"type": "integer", "default": 400},
        },
        "required": ["content_text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "llm_used": {"type": "boolean"},
        },
    },
    agent_factory=SummarizerAgent,
)
