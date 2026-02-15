"""Ollama LLM client — call /api/generate with timeout + retry."""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger("echogarden.llm.ollama")

EG_OLLAMA_URL: str = os.environ.get(
    "EG_OLLAMA_URL", "http://host.docker.internal:11434"
)
EG_OLLAMA_MODEL: str = os.environ.get("EG_OLLAMA_MODEL", "phi3:mini")
_OLLAMA_TIMEOUT: float = float(os.environ.get("EG_OLLAMA_TIMEOUT", "180"))


class LLMUnavailableError(Exception):
    """Raised when the LLM backend is unreachable."""


async def ping_ollama() -> bool:
    """Return True if Ollama is reachable and has at least one model."""
    if not EG_OLLAMA_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{EG_OLLAMA_URL}/api/tags")
            return r.status_code == 200
    except Exception:
        return False


async def ollama_generate(
    prompt: str,
    *,
    system: str | None = None,
    timeout: float = _OLLAMA_TIMEOUT,
    num_predict: int | None = None,
) -> str:
    """Call Ollama /api/generate and return the response text.

    Raises LLMUnavailableError if the server is unreachable or times out.
    """
    if not EG_OLLAMA_URL:
        raise LLMUnavailableError("EG_OLLAMA_URL not configured")

    body: dict = {
        "model": EG_OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        body["system"] = system
    if num_predict is not None:
        body.setdefault("options", {})["num_predict"] = num_predict

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{EG_OLLAMA_URL}/api/generate", json=body)
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(f"Ollama HTTP error: {exc}") from exc
    except Exception as exc:
        raise LLMUnavailableError(f"Ollama error: {exc}") from exc


async def ollama_generate_json(
    prompt: str,
    *,
    system: str | None = None,
    timeout: float = _OLLAMA_TIMEOUT,
    num_predict: int | None = None,
) -> str:
    """Call Ollama /api/generate with JSON format requested."""
    if not EG_OLLAMA_URL:
        raise LLMUnavailableError("EG_OLLAMA_URL not configured")

    body: dict = {
        "model": EG_OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }
    if system:
        body["system"] = system
    if num_predict is not None:
        body.setdefault("options", {})["num_predict"] = num_predict

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.post(f"{EG_OLLAMA_URL}/api/generate", json=body)
            r.raise_for_status()
            data = r.json()
            return data.get("response", "")
    except httpx.HTTPError as exc:
        raise LLMUnavailableError(f"Ollama HTTP error: {exc}") from exc
    except Exception as exc:
        raise LLMUnavailableError(f"Ollama error: {exc}") from exc


async def llm_available() -> bool:
    """Check if Ollama LLM is available."""
    return await ping_ollama()
