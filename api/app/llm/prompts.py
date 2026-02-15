"""Prompt templates for Phase 6 LLM agents (summarizer + extractor)."""

from __future__ import annotations


def summarizer_prompt(content_text: str, title: str | None, max_chars: int = 400) -> str:
    """Build the summarizer prompt."""
    title_line = f"Title: {title}\n" if title else ""
    # Truncate input to keep prompt small for fast local LLM inference
    truncated = content_text[:3000]
    return (
        f"{title_line}"
        f"Text:\n{truncated}\n\n"
        f"Summarize the above text in 1-3 sentences. "
        f"Maximum {max_chars} characters. "
        f"Preserve key entities, decisions, and facts. "
        f"Do not use bullet lists unless absolutely necessary. "
        f"Return ONLY the summary text, nothing else."
    )


def extractor_system() -> str:
    """System prompt for the extractor."""
    return (
        "You are a structured information extraction engine. "
        "You always return valid JSON and nothing else."
    )


def extractor_prompt(
    content_text: str,
    title: str | None,
    max_entities: int = 30,
) -> str:
    """Build the extractor prompt for entities/tags/actions."""
    title_line = f"Title: {title}\n" if title else ""
    truncated = content_text[:3000]
    return (
        f"{title_line}"
        f"Text:\n{truncated}\n\n"
        f"Extract structured information from the above text. "
        f"Return STRICT JSON with exactly these keys:\n"
        f'{{\n'
        f'  "entities": [  // max {max_entities} items\n'
        f'    {{"name": "string", "type": "Person|Org|Project|Topic|Place|Other", "confidence": 0.0-1.0}}\n'
        f'  ],\n'
        f'  "tags": ["string"],  // max 12 items, short topic tags\n'
        f'  "actions": [  // max 10 items, tasks or action items found\n'
        f'    {{"text": "string", "due": "YYYY-MM-DD or null", "priority": "high|medium|low|null"}}\n'
        f'  ]\n'
        f'}}\n\n'
        f"Rules:\n"
        f"- Prefer meaningful entities: real people, organizations, projects, topics, places.\n"
        f"- Confidence should reflect how clearly the entity is mentioned.\n"
        f"- Do NOT include generic words, stopwords, or formatting artifacts as entities.\n"
        f"- Tags should be short lowercase topic labels.\n"
        f"- Return valid JSON only. No markdown, no explanation."
    )


def extractor_retry_prompt() -> str:
    """Retry prompt when initial extraction returns invalid JSON."""
    return (
        "Your previous response was not valid JSON. "
        "Return ONLY valid JSON with keys: entities, tags, actions. "
        "No markdown code fences, no explanation, just the JSON object."
    )
