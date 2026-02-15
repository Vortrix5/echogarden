"""Router: Chat — Phase 7 grounded Q&A loop."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.orchestrator.models import StepResult
from app.orchestrator.orchestrator import Orchestrator

router = APIRouter(tags=["chat"])
_orch = Orchestrator()


# ── Request / Response models ─────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="User question")
    top_k: int = Field(default=8, ge=1, le=50)
    use_graph: bool = True
    hops: int = Field(default=1, ge=0, le=3)


class CitationOut(BaseModel):
    memory_id: str = ""
    quote: str = ""
    source_type: str = ""
    created_at: str = ""


class EvidenceOut(BaseModel):
    memory_id: str = ""
    summary: str = ""
    snippet: str = ""
    score: float = 0.0
    reasons: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    verdict: str = ""
    citations: list[CitationOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"


# ── Endpoint ─────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Grounded Q&A: retrieval → weaver → verifier → answer + citations + trace.

    Delegates entirely to Orchestrator.chat() which persists
    CONVERSATION_TURN, CHAT_CITATION, TOOL_CALL, EXEC_NODE, EXEC_EDGE, and EXEC_TRACE.
    """
    result = await _orch.chat(
        req.message,
        top_k=req.top_k,
        use_graph=req.use_graph,
        hops=req.hops,
    )

    return ChatResponse(
        trace_id=result.trace_id,
        answer=result.answer,
        verdict=result.verdict,
        citations=[CitationOut(**c) for c in result.citations],
        evidence=[EvidenceOut(**e) for e in result.evidence],
        steps=result.steps,
        status=result.status,
    )
