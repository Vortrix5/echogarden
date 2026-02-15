"""Optional Ollama LLM client with stub fallback.

Phase 6: Delegates core LLM calls to app.llm.ollama_client.
Phase 7: Grounded weave/verify using structured prompts + JSON-mode.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from app.llm.ollama_client import (
    LLMUnavailableError,
    llm_available,
    ollama_generate,
    ollama_generate_json,
    ping_ollama,
    EG_OLLAMA_URL,
    EG_OLLAMA_MODEL,
)
from app.llm.prompts import (
    format_evidence_block,
    verifier_prompt,
    verifier_system,
    weaver_prompt,
    weaver_system,
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


def _parse_json(raw: str) -> dict | None:
    """Best-effort JSON parse from LLM output."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


# ── Phase 7 — grounded weaver ────────────────────────────

async def weave_with_llm(question: str, evidence: list[dict]) -> dict:
    """Use the LLM to produce a grounded answer with citations.

    Falls back to stub if LLM is unavailable.
    """
    try:
        evidence_block = format_evidence_block(evidence, max_chars=400)
        prompt = weaver_prompt(question, evidence_block, max_citations=8)
        system = weaver_system()

        raw = await ollama_generate_json(prompt, system=system, timeout=15.0)
        parsed = _parse_json(raw)

        if parsed and "answer" in parsed:
            # Validate citation memory_ids
            valid_ids = {e.get("memory_id") for e in evidence}
            citations = [
                c for c in parsed.get("citations", [])
                if isinstance(c, dict) and c.get("memory_id") in valid_ids
            ]
            return {
                "answer": parsed["answer"],
                "citations": citations[:8],
                "llm_used": True,
            }
        # Fallback: use raw text as answer
        return {"answer": raw.strip()[:2000], "citations": [], "llm_used": True}
    except LLMUnavailableError:
        logger.info("LLM unavailable — falling back to stub weaver")
        return _stub_weave(question, evidence)


def _stub_weave(question: str, evidence: list[dict]) -> dict:
    """Deterministic stub when no LLM."""
    if not evidence:
        return {
            "answer": "I could not find any relevant memories to answer this question.",
            "citations": [],
            "llm_used": False,
        }
    bullets = []
    citations = []
    for ev in evidence[:8]:
        mid = ev.get("memory_id", "?")
        summary = ev.get("summary", "(no summary)")
        bullets.append(f"- [{mid}] {summary}")
        citations.append({"memory_id": mid, "quote": summary[:120]})
    answer = "Here are the most relevant memories I found:\n" + "\n".join(bullets)
    return {"answer": answer, "citations": citations, "llm_used": False}


# ── Phase 7 — grounded verifier ──────────────────────────

async def verify_with_llm(question: str, answer: str, evidence: list[dict]) -> dict:
    """Use the LLM to verify groundedness.

    Falls back to heuristic if LLM is unavailable.
    """
    try:
        evidence_block = format_evidence_block(evidence, max_chars=400)
        prompt = verifier_prompt(question, answer, evidence_block)
        system = verifier_system()

        raw = await ollama_generate_json(prompt, system=system, timeout=10.0)
        parsed = _parse_json(raw)

        if parsed and "verdict" in parsed:
            verdict = parsed["verdict"]
            if verdict not in ("pass", "revise", "abstain"):
                verdict = "pass"
            return {
                "verdict": verdict,
                "revised_answer": parsed.get("revised_answer", ""),
                "issues": parsed.get("issues", []),
                "llm_used": True,
            }
        return {"verdict": "pass", "issues": [], "revised_answer": "", "llm_used": True}
    except LLMUnavailableError:
        logger.info("LLM unavailable — falling back to heuristic verifier")
        return _heuristic_verify(answer, evidence)


def _heuristic_verify(answer: str, evidence: list[dict]) -> dict:
    """Heuristic verifier when no LLM is available."""
    if not evidence:
        return {
            "verdict": "abstain",
            "revised_answer": "",
            "issues": ["No evidence available."],
            "llm_used": False,
        }
    has_citations = bool(re.search(r"\[[\w-]{8,}\]", answer))
    if not has_citations:
        return {
            "verdict": "revise",
            "revised_answer": "",
            "issues": ["Answer contains no citations to evidence."],
            "llm_used": False,
        }
    return {"verdict": "pass", "revised_answer": "", "issues": [], "llm_used": False}
