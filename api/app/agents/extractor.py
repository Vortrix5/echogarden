"""ExtractorAgent — extract entities, tags, and actions via local LLM."""

from __future__ import annotations

import json
import logging
import re

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry
from app.llm.ollama_client import (
    LLMUnavailableError,
    llm_available,
    ollama_generate_json,
    ollama_generate,
)
from app.llm.prompts import extractor_prompt, extractor_retry_prompt, extractor_system
from app.graph.canonicalize import normalize_entity_type

logger = logging.getLogger("echogarden.agents.extractor")

_VALID_ENTITY_TYPES = {"Person", "Org", "Project", "Topic", "Place", "Technology", "Component", "Other"}
_MIN_CONFIDENCE = 0.55
_MAX_ENTITIES = 30
_MAX_TAGS = 12
_MAX_ACTIONS = 10


def _try_parse_json(raw: str) -> dict | None:
    """Best-effort JSON parse — strip markdown fences if present."""
    text = raw.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _normalize_entity_name(name: str, entity_type: str) -> str:
    """Normalize entity name based on type."""
    name = " ".join(name.strip().split())  # collapse spaces
    if entity_type in ("Person", "Org", "Project"):
        return name.title()
    return name


def _validate_and_clean(data: dict) -> dict:
    """Validate and enforce caps on extracted data."""
    entities = []
    for ent in data.get("entities", [])[:_MAX_ENTITIES]:
        if not isinstance(ent, dict):
            continue
        name = str(ent.get("name", "")).strip()
        if not name or len(name) < 2:
            continue
        etype = normalize_entity_type(str(ent.get("type", "Other")))
        if etype not in _VALID_ENTITY_TYPES:
            etype = "Other"
        confidence = float(ent.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))
        if confidence < _MIN_CONFIDENCE:
            continue
        entities.append({
            "name": _normalize_entity_name(name, etype),
            "type": etype,
            "confidence": round(confidence, 2),
        })

    tags = []
    for tag in data.get("tags", [])[:_MAX_TAGS]:
        t = str(tag).strip().lower()
        if t and len(t) >= 2:
            tags.append(t)

    actions = []
    for act in data.get("actions", [])[:_MAX_ACTIONS]:
        if not isinstance(act, dict):
            continue
        text = str(act.get("text", "")).strip()
        if not text:
            continue
        actions.append({
            "text": text,
            "due": act.get("due") or None,
            "priority": act.get("priority") or None,
        })

    return {
        "entities": entities,
        "tags": tags,
        "actions": actions,
    }


def _empty_extraction() -> dict:
    """Return empty extraction result."""
    return {"entities": [], "tags": [], "actions": []}


class ExtractorAgent(BasePassiveAgent):
    name = "extractor"
    version = "0.6.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        content_text: str = envelope.inputs.get("content_text", "")
        title: str | None = envelope.inputs.get("title")
        max_entities: int = envelope.inputs.get("max_entities", _MAX_ENTITIES)

        if not content_text.strip():
            return _empty_extraction()

        try:
            if not await llm_available():
                raise LLMUnavailableError("LLM not available")

            prompt = extractor_prompt(content_text, title, max_entities)
            system = extractor_system()

            # First attempt — request JSON format
            raw = await ollama_generate_json(
                prompt, system=system, timeout=120.0, num_predict=768,
            )
            parsed = _try_parse_json(raw)

            # Retry once if invalid
            if parsed is None:
                logger.warning("Extractor: invalid JSON on first attempt, retrying")
                retry_prompt = prompt + "\n\n" + extractor_retry_prompt()
                raw = await ollama_generate(
                    retry_prompt, timeout=60.0, num_predict=768,
                )
                parsed = _try_parse_json(raw)

            if parsed is None:
                logger.warning("Extractor: invalid JSON after retry, returning empty")
                return _empty_extraction()

            result = _validate_and_clean(parsed)
            logger.info(
                "Extracted %d entities, %d tags, %d actions",
                len(result["entities"]),
                len(result["tags"]),
                len(result["actions"]),
            )
            return result

        except (LLMUnavailableError, Exception) as exc:
            logger.info("LLM failed (%s) — returning empty extraction", type(exc).__name__)
            return _empty_extraction()


registry.register(
    name="extractor",
    version="0.6.0",
    description="Extract entities, tags, and actions from text via local LLM. Returns empty on LLM failure.",
    input_schema={
        "type": "object",
        "properties": {
            "content_text": {"type": "string"},
            "title": {"type": ["string", "null"]},
            "max_entities": {"type": "integer", "default": 30},
        },
        "required": ["content_text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string"},
                        "confidence": {"type": "number"},
                    },
                },
            },
            "tags": {"type": "array", "items": {"type": "string"}},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "due": {"type": ["string", "null"]},
                        "priority": {"type": ["string", "null"]},
                    },
                },
            },
        },
    },
    agent_factory=ExtractorAgent,
)
