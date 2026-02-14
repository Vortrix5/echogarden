"""GraphBuilderAgent — structured entity extraction for property graph."""

from __future__ import annotations

import re

from app.agents.base import BasePassiveAgent
from app.core.tool_contracts import ToolEnvelope
from app.core.tool_registry import registry

# Common English stopwords (capitalized forms) to exclude.
_STOPWORDS = frozenset({
    "THE", "AND", "BUT", "FOR", "NOR", "YET", "WITH", "FROM",
    "INTO", "UPON", "ABOUT", "AFTER", "BEFORE", "DURING", "THROUGH",
    "BETWEEN", "WITHOUT", "WITHIN", "ALONG", "AMONG", "ABOVE", "BELOW",
    "THIS", "THAT", "THESE", "THOSE", "WILL", "WOULD", "COULD", "SHOULD",
    "HAVE", "HAS", "HAD", "BEEN", "BEING", "ARE", "WAS", "WERE", "NOT",
    "ALL", "ANY", "EACH", "EVERY", "BOTH", "FEW", "MORE", "MOST", "OTHER",
    "SOME", "SUCH", "THAN", "TOO", "VERY", "CAN", "JUST", "DON", "NOW",
    "HER", "HIM", "HIS", "HOW", "ITS", "LET", "MAY", "OUR", "OWN",
    "SAY", "SHE", "WHO", "WHY", "YOU", "DID", "GET", "GOT", "ONE",
    "TWO", "NEW", "OLD", "SEE", "WAY", "USE", "HER", "HIS", "ALSO",
})

# Multi-word capitalized phrase pattern
_PHRASE_RE = re.compile(r"\b(?:[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+)\b")
_WORD_RE = re.compile(r"\b[A-Z][A-Za-z]{2,}\b")

# Simple patterns for structured extraction
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_DATE_RE = re.compile(
    r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s*\d{4}\b",
    re.IGNORECASE,
)


def _extract_entities(text: str) -> list[dict]:
    """Extract structured entities from text."""
    entities: list[dict] = []
    seen: set[str] = set()

    # Multi-word phrases (higher confidence)
    for match in _PHRASE_RE.finditer(text):
        phrase = match.group()
        key = phrase.upper()
        if key not in seen and all(w.upper() not in _STOPWORDS for w in phrase.split()):
            seen.add(key)
            entities.append({"label": phrase, "entity_type": "Phrase", "confidence": 0.6})

    # Single capitalized words
    for match in _WORD_RE.finditer(text):
        word = match.group()
        key = word.upper()
        if key not in _STOPWORDS and key not in seen:
            seen.add(key)
            entities.append({"label": word, "entity_type": "Entity", "confidence": 0.3})

    # URLs
    for match in _URL_RE.finditer(text):
        url = match.group()
        if url not in seen:
            seen.add(url)
            entities.append({"label": url, "entity_type": "URL", "confidence": 0.9})

    # Emails
    for match in _EMAIL_RE.finditer(text):
        email = match.group()
        if email not in seen:
            seen.add(email)
            entities.append({"label": email, "entity_type": "Email", "confidence": 0.9})

    # Dates
    for match in _DATE_RE.finditer(text):
        date_str = match.group()
        if date_str not in seen:
            seen.add(date_str)
            entities.append({"label": date_str, "entity_type": "Date", "confidence": 0.7})

    return entities


class GraphBuilderAgent(BasePassiveAgent):
    name = "graph_builder"
    version = "0.1.0"

    async def execute(self, envelope: ToolEnvelope) -> dict:
        content_text: str = envelope.inputs.get("content_text", "")
        memory_id: str = envelope.inputs.get("memory_id", "")
        call_id: str = envelope.inputs.get("_call_id", "")

        entities = _extract_entities(content_text)

        nodes: list[dict] = []
        edges: list[dict] = []

        for ent in entities:
            label = ent["label"]
            ent_type = ent["entity_type"]
            confidence = ent["confidence"]
            ent_id = f"ent:{label.lower().replace(' ', '_')}"

            nodes.append({
                "node_id": ent_id,
                "node_type": ent_type,
                "props": {"label": label, "entity_type": ent_type},
            })
            if memory_id:
                mem_node_id = f"mem:{memory_id}"
                edges.append({
                    "from_node_id": mem_node_id,
                    "to_node_id": ent_id,
                    "edge_type": "MENTIONS",
                    "weight": confidence,
                    "provenance": {
                        "created_by": "GraphBuilderAgent",
                        "tool_call_id": call_id,
                        "confidence": confidence,
                        "migrated": False,
                    },
                })

        return {"nodes": nodes, "edges": edges}


registry.register(
    name="graph_builder",
    version="0.1.0",
    description="Build knowledge-graph nodes and edges from content text (structured extraction).",
    input_schema={"type": "object", "properties": {"content_text": {"type": "string"}}},
    output_schema={
        "type": "object",
        "properties": {
            "nodes": {"type": "array"},
            "edges": {"type": "array"},
        },
    },
    agent_factory=GraphBuilderAgent,
)
