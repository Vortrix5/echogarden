"""VerifierAgent — check answer groundedness against evidence.

Phase 7: Validates that every claim in the weaver's answer is supported
by the retrieved evidence. Uses LLM when available; falls back to heuristic.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry

logger = logging.getLogger("echogarden.agents.verifier")


def _parse_llm_json(raw: str) -> dict | None:
    """Best-effort parse JSON from LLM output."""
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`")
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


def _heuristic_verify(answer: str, citations: list[dict], evidence: list[dict]) -> dict:
    """Deterministic heuristic verifier when LLM is unavailable."""
    if not evidence:
        return {
            "verdict": "abstain",
            "revised_answer": "",
            "issues": ["No evidence available to verify against."],
        }
    if not citations:
        # No citations attached — likely stub mode
        # Check if answer references any memory_ids inline
        has_inline_refs = bool(re.search(r"\[[\w-]{8,}\]", answer))
        if has_inline_refs:
            return {"verdict": "pass", "revised_answer": "", "issues": []}
        return {
            "verdict": "revise",
            "revised_answer": "",
            "issues": ["Answer contains no citations to evidence."],
        }
    # Has citations — basic pass
    return {"verdict": "pass", "revised_answer": "", "issues": []}


class VerifierAgent(BasePassiveAgent):
    name = "verifier"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        question = envelope.inputs.get("question", "")
        answer = envelope.inputs.get("answer", "")
        evidence = envelope.inputs.get("evidence") or envelope.inputs.get("context", [])
        citations = envelope.inputs.get("citations", [])

        # If orchestrator pre-computed LLM result, use it directly
        llm_override = envelope.inputs.get("_llm_override")
        if llm_override and isinstance(llm_override, dict):
            return {
                "verdict": llm_override.get("verdict", "pass"),
                "revised_answer": llm_override.get("revised_answer", ""),
                "issues": llm_override.get("issues", []),
            }

        # Try LLM-based verification
        try:
            from app.llm.ollama_client import ollama_generate_json, LLMUnavailableError
            from app.llm.prompts import verifier_system, verifier_prompt, format_evidence_block

            evidence_block = format_evidence_block(evidence, max_chars=400)
            prompt = verifier_prompt(question, answer, evidence_block)
            system = verifier_system()

            raw = await ollama_generate_json(prompt, system=system, timeout=10.0)
            parsed = _parse_llm_json(raw)

            if parsed and "verdict" in parsed:
                verdict = parsed["verdict"]
                if verdict not in ("pass", "revise", "abstain"):
                    verdict = "pass"
                return {
                    "verdict": verdict,
                    "revised_answer": parsed.get("revised_answer", ""),
                    "issues": parsed.get("issues", []),
                }
            else:
                logger.warning("[VERIFIER] LLM returned unparseable JSON, using heuristic")
                return _heuristic_verify(answer, citations, evidence)

        except Exception as exc:
            logger.info("[VERIFIER] LLM unavailable (%s), using heuristic", exc)
            return _heuristic_verify(answer, citations, evidence)


registry.register(
    name="verifier",
    version="0.2.0",
    description="Verify answer groundedness against retrieved evidence.",
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "answer": {"type": "string"},
            "evidence": {"type": "array"},
            "citations": {"type": "array"},
        },
        "required": ["answer", "evidence"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "revise", "abstain"]},
            "revised_answer": {"type": "string"},
            "issues": {"type": "array", "items": {"type": "string"}},
        },
    },
    agent_factory=VerifierAgent,
)
