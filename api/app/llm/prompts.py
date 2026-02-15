"""Prompt templates for Phase 6 LLM agents (summarizer + extractor)
and Phase 7 grounded Q&A (weaver + verifier)."""

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


# ── Phase 7: Weaver ──────────────────────────────────────

def weaver_system() -> str:
    """System prompt for the grounded weaver."""
    return (
        "You are a precise knowledge assistant. You answer questions using "
        "ONLY the evidence provided. Follow these rules strictly:\n"
        "1. Every factual claim MUST cite at least one memory_id from the evidence.\n"
        "2. Use the format [memory_id] for citations inline.\n"
        "3. If the evidence is insufficient to answer, say so explicitly.\n"
        "4. Keep the answer concise — 1-4 sentences when possible.\n"
        "5. Never fabricate information not present in the evidence.\n"
        "6. Return STRICT JSON only, no markdown."
    )


def weaver_prompt(question: str, evidence_block: str, max_citations: int = 8) -> str:
    """Build the weaver prompt with formatted evidence."""
    return (
        f"Evidence:\n{evidence_block}\n\n"
        f"Question: {question}\n\n"
        f"Return a JSON object with exactly these keys:\n"
        f'{{\n'
        f'  "answer": "Your grounded answer with inline [memory_id] citations",\n'
        f'  "citations": [\n'
        f'    {{"memory_id": "...", "quote": "exact short quote from evidence"}}\n'
        f"  ]  // max {max_citations} citations\n"
        f'}}\n\n'
        f"Rules:\n"
        f"- Use ONLY information from the evidence above.\n"
        f"- Every factual claim must cite a memory_id.\n"
        f"- If evidence is insufficient, set answer to explain what is missing.\n"
        f"- Return valid JSON only. No markdown, no explanation."
    )


def format_evidence_block(evidence: list[dict], max_chars: int = 400) -> str:
    """Format evidence list into a text block for the LLM prompt.
    
    Limits to top 3 evidence items to keep prompt small and reduce hallucination.
    """
    import os
    lines: list[str] = []
    for i, ev in enumerate(evidence[:3], 1):
        mid = ev.get("memory_id", "?")
        summary = ev.get("summary", "")
        content = ev.get("content_text", "")
        source_type = ev.get("source_type", "unknown")
        created_at = ev.get("created_at", "")
        # Derive a human-readable filename
        file_path = ev.get("file_path", "")
        if not file_path:
            meta = ev.get("metadata") or {}
            if isinstance(meta, dict):
                file_path = meta.get("file_path", "")
        label = os.path.basename(file_path) if file_path else (summary[:40] or mid[:12])
        # Use first max_chars of content, or summary if no content
        snippet = (content[:max_chars] if content else summary)[:max_chars]
        lines.append(
            f"[{i}] memory_id={mid} | file={label} | source={source_type} | date={created_at}\n"
            f"    {snippet}"
        )
    return "\n\n".join(lines)


# ── Phase 7: Verifier ────────────────────────────────────

def verifier_system() -> str:
    """System prompt for the verifier."""
    return (
        "You are a fact-checking agent. You verify whether an answer is fully "
        "supported by the provided evidence. Follow these rules strictly:\n"
        "1. Check each claim in the answer against the evidence.\n"
        "2. Mark any unsupported claims.\n"
        "3. If unsupported claims can be removed to save the answer, revise it.\n"
        "4. If the core answer is unsupported, set verdict to 'abstain'.\n"
        "5. Return STRICT JSON only, no markdown."
    )


def verifier_prompt(question: str, answer: str, evidence_block: str) -> str:
    """Build the verifier prompt."""
    return (
        f"Evidence:\n{evidence_block}\n\n"
        f"Question: {question}\n"
        f"Answer to verify: {answer}\n\n"
        f"Return a JSON object with exactly these keys:\n"
        f'{{\n'
        f'  "verdict": "pass" or "revise" or "abstain",\n'
        f'  "revised_answer": "corrected answer if verdict=revise, else empty string",\n'
        f'  "issues": ["description of each unsupported claim"]\n'
        f'}}\n\n'
        f"Rules:\n"
        f"- verdict='pass' if every claim is supported by evidence.\n"
        f"- verdict='revise' if some claims are unsupported but can be removed.\n"
        f"- verdict='abstain' if the core answer is unsupported.\n"
        f"- Return valid JSON only. No markdown, no explanation."
    )
