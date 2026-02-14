"""Pydantic models for the tool-call envelope and results."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PrivacyMode(str, Enum):
    local_only = "local_only"
    redact = "redact"
    none = "none"


class ToolStatus(str, Enum):
    ok = "ok"
    error = "error"
    timeout = "timeout"


# ── Constraints ───────────────────────────────────────────
class ToolConstraints(BaseModel):
    timeout_ms: int = Field(default=8000, ge=100, le=300_000)
    max_output_bytes: int = Field(default=200_000, ge=1)
    privacy_mode: PrivacyMode = PrivacyMode.local_only


# ── Envelope (request) ───────────────────────────────────
class ToolEnvelope(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    span_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    caller: str = "api"
    callee: str  # tool name
    intent: str | None = None
    idempotency_key: str | None = None
    constraints: ToolConstraints = Field(default_factory=ToolConstraints)
    inputs: dict[str, Any] = Field(default_factory=dict)


# ── Error detail ──────────────────────────────────────────
class ToolErrorDetail(BaseModel):
    type: str
    message: str


# ── Result (response) ────────────────────────────────────
class ToolResult(BaseModel):
    trace_id: str
    span_id: str
    tool_name: str
    status: ToolStatus
    outputs: dict[str, Any] = Field(default_factory=dict)
    error: ToolErrorDetail | None = None
    started_at: str
    finished_at: str
    elapsed_ms: int


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
