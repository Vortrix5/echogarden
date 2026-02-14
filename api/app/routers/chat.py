"""Router: Chat — delegates to the Active Orchestrator."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.orchestrator.models import StepResult
from app.orchestrator.orchestrator import Orchestrator

router = APIRouter(tags=["chat"])
_orch = Orchestrator()


class ChatRequest(BaseModel):
    user_text: str


class ChatResponse(BaseModel):
    answer: str
    citations: list
    verdict: str = ""
    trace_id: str
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Chat pipeline: security_check -> retrieval -> weave -> verify.

    Delegates entirely to Orchestrator.chat() which persists
    CONVERSATION_TURN, TOOL_CALL, EXEC_NODE, EXEC_EDGE, and EXEC_TRACE.
    """
    result = await _orch.chat(req.user_text)

    return ChatResponse(
        answer=result.answer,
        citations=result.citations,
        verdict=result.verdict,
        trace_id=result.trace_id,
        steps=result.steps,
        status=result.status,
    )
