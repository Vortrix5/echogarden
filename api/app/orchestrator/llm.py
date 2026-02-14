"""Optional Ollama LLM client with stub fallback."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("echogarden.llm")

EG_OLLAMA_URL: str = os.environ.get("EG_OLLAMA_URL", "")
EG_OLLAMA_MODEL: str = os.environ.get("EG_OLLAMA_MODEL", "phi3:mini")
_OLLAMA_TIMEOUT: float = 60.0  # seconds


class LLMUnavailableError(Exception):
    """Raised when the LLM backend is unreachable."""


async def ping_ollama() -> bool:
    """Return True if Ollama is reachable."""
    if not EG_OLLAMA_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{EG_OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def ollama_generate(prompt: str, *, timeout: float = _OLLAMA_TIMEOUT) -> str:
    """Call Ollama /api/generate and return the response text.

    Raises LLMUnavailableError if the server is unreachable.
    """
    if not EG_OLLAMA_URL:
        raise LLMUnavailableError("EG_OLLAMA_URL not configured")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(
                f"{EG_OLLAMA_URL}/api/generate",
                json={
                    "model": EG_OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            r.raise_for_status()
            data: dict[str, Any] = r.json()
            return data.get("response", "")
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(f"Ollama HTTP error: {exc}") from exc
    except Exception as exc:
        raise LLMUnavailableError(f"Ollama error: {exc}") from exc


async def llm_available() -> bool:
    """Check availability at module level (cached per-call)."""
    return await ping_ollama()


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
