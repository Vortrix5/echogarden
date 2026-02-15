"""Optional Ollama LLM client with stub fallback.

Phase 6: Delegates core LLM calls to app.llm.ollama_client.
This module retains the weave/verify convenience wrappers used by the chat pipeline.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.llm.ollama_client import (
    LLMUnavailableError,
    llm_available,
    ollama_generate,
    ping_ollama,
    EG_OLLAMA_URL,
    EG_OLLAMA_MODEL,
)

logger = logging.getLogger("echogarden.llm")

# Re-export for backward compatibility
__all__ = [
    "LLMUnavailableError",
    "llm_available",
    "ollama_generate",
    "ping_ollama",
    "weave_with_llm",
    "verify_with_llm",
]


# ── Convenience wrappers used by the orchestrator ─────────

async def weave_with_llm(query: str, context: list[dict]) -> dict:
    """Use the LLM to weave context into an answer.

    Falls back to stub if LLM is unavailable.
    """
    try:
        context_text = "\n".join(
            c.get("summary", str(c)) for c in context[:20]
        )
        prompt = (
            "You are a helpful knowledge assistant. Using ONLY the context below, "
            "answer the user's question. Include citations in [1], [2] style.\n\n"
            f"Context:\n{context_text}\n\n"
            f"Question: {query}\n\nAnswer:"
        )
        answer = await ollama_generate(prompt)
        return {"answer": answer, "citations": [], "llm_used": True}
    except LLMUnavailableError:
        logger.info("LLM unavailable — falling back to stub weaver")
        return {"answer": "(stub answer)", "citations": [], "llm_used": False}


async def verify_with_llm(answer: str, context: list[dict]) -> dict:
    """Use the LLM to verify an answer.

    Falls back to basic heuristic if LLM is unavailable.
    """
    try:
        context_text = "\n".join(
            c.get("summary", str(c)) for c in context[:20]
        )
        prompt = (
            "Check whether the following answer is supported by the context. "
            "Reply with JSON: {\"verdict\": \"pass\" or \"fail\", \"issues\": [...]}\n\n"
            f"Context:\n{context_text}\n\n"
            f"Answer:\n{answer}\n\nVerification:"
        )
        raw = await ollama_generate(prompt, timeout=30.0)
        # Best-effort parse
        import json
        try:
            result = json.loads(raw)
            return {
                "verdict": result.get("verdict", "pass"),
                "issues": result.get("issues", []),
                "llm_used": True,
            }
        except json.JSONDecodeError:
            return {"verdict": "pass", "issues": [], "llm_used": True}
    except LLMUnavailableError:
        logger.info("LLM unavailable — falling back to basic verifier")
        # Basic heuristic: if answer has no citations or is very short, flag it
        needs_review = len(answer) < 20 or "[" not in answer
        return {
            "verdict": "needs_review" if needs_review else "pass",
            "issues": ["no_citations"] if needs_review else [],
            "llm_used": False,
        }
