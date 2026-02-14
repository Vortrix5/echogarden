"""Plan / result models for the Active Orchestrator."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class PipelineType(str, Enum):
    doc_parse = "doc_parse"
    ocr = "ocr"
    asr = "asr"


class ToolStep(BaseModel):
    """One step in an orchestration plan."""
    tool_name: str
    intent: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 8000
    depends_on: list[str] = Field(default_factory=list)


class OrchestrationPlan(BaseModel):
    """Describes the full pipeline the orchestrator will execute."""
    trace_id: str
    pipeline: PipelineType
    steps: list[ToolStep]


class StepResult(BaseModel):
    """Result of a single orchestrated tool step."""
    tool_name: str
    call_id: str
    exec_node_id: str
    status: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    elapsed_ms: int = 0
    error: str | None = None


class IngestResult(BaseModel):
    """Result of the full ingestion pipeline."""
    trace_id: str
    pipeline: str
    memory_id: str | None = None
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"


class ChatResult(BaseModel):
    """Result of the full chat pipeline."""
    trace_id: str
    answer: str = ""
    citations: list[Any] = Field(default_factory=list)
    verdict: str = ""
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"
