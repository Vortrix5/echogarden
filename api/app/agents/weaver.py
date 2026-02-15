"""WeaverAgent — grounded Q&A answer generation.

Phase 7: Produces an answer grounded ONLY in retrieved evidence.
Uses LLM (Ollama) when available; falls back to a deterministic stub.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry

logger = logging.getLogger("echogarden.agents.weaver")


def _build_snippet(ev: dict, max_chars: int = 800) -> str:
    """Return the best available text excerpt from an evidence dict."""
    content = ev.get("content_text") or ""
    summary = ev.get("summary") or ""
    text = content if content else summary
    return text[:max_chars]


def _stub_weave(question: str, evidence: list[dict]) -> dict:
    """Deterministic stub when LLM is unavailable."""
    if not evidence:
        return {
            "answer": "I could not find any relevant memories to answer this question.",
            "citations": [],
        }
    bullets = []
    citations = []
    for ev in evidence[:8]:
        mid = ev.get("memory_id", "?")
        summary = ev.get("summary", "(no summary)")
        bullets.append(f"- [{mid}] {summary}")
        citations.append({"memory_id": mid, "quote": summary[:120]})
    answer = (
        "Here are the most relevant memories I found:\n"
        + "\n".join(bullets)
    )
    return {"answer": answer, "citations": citations}


def _parse_llm_json(raw: str) -> dict | None:
    """Best-effort parse JSON from LLM output (handles markdown fences)."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", raw)
    cleaned = cleaned.strip().rstrip("`")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in output
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


class WeaverAgent(BasePassiveAgent):
    name = "weaver"
    version = "0.2.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        question = envelope.inputs.get("question") or envelope.inputs.get("query", "")
        evidence = envelope.inputs.get("evidence") or envelope.inputs.get("context", [])
        max_citations = envelope.inputs.get("max_citations", 8)

        # If orchestrator pre-computed LLM result, use it directly
        llm_override = envelope.inputs.get("_llm_override")
        if llm_override and isinstance(llm_override, dict):
            return {
                "answer": llm_override.get("answer", ""),
                "citations": llm_override.get("citations", []),
            }

        # Otherwise, try LLM then fall back to stub
        try:
            from app.llm.ollama_client import ollama_generate_json, LLMUnavailableError
            from app.llm.prompts import weaver_system, weaver_prompt, format_evidence_block

            evidence_block = format_evidence_block(evidence, max_chars=400)
            prompt = weaver_prompt(question, evidence_block, max_citations)
            system = weaver_system()

            raw = await ollama_generate_json(prompt, system=system, timeout=15.0)
            parsed = _parse_llm_json(raw)

            if parsed and "answer" in parsed:
                citations = parsed.get("citations", [])
                # Validate citation memory_ids against evidence
                valid_ids = {e.get("memory_id") for e in evidence}
                validated_citations = [
                    c for c in citations
                    if isinstance(c, dict) and c.get("memory_id") in valid_ids
                ]
                return {
                    "answer": parsed["answer"],
                    "citations": validated_citations[:max_citations],
                }
            else:
                logger.warning("[WEAVER] LLM returned unparseable JSON, using stub")
                return _stub_weave(question, evidence)

        except Exception as exc:
            logger.info("[WEAVER] LLM unavailable (%s), using stub", exc)
            return _stub_weave(question, evidence)


registry.register(
    name="weaver",
    version="0.2.0",
    description="Weave retrieved evidence into a grounded answer with citations.",
    input_schema={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                        "summary": {"type": "string"},
                        "content_text": {"type": "string"},
                    },
                },
            },
            "max_citations": {"type": "integer", "default": 8},
        },
        "required": ["question", "evidence"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "answer": {"type": "string"},
            "citations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                        "quote": {"type": "string"},
                    },
                },
            },
        },
    },
    agent_factory=WeaverAgent,
)
