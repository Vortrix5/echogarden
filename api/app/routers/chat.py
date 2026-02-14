"""Router: Chat stub orchestrator."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.tool_contracts import ToolEnvelope, ToolResult
from app.core.tool_registry import registry
from app.db.repo import insert_conversation_turn

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    user_text: str


class ChatResponse(BaseModel):
    answer: str
    citations: list
    trace_id: str
    steps: list[ToolResult]


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Minimal chat orchestrator: Retrieval -> Weaver -> Verifier.

    Persists a CONVERSATION_TURN and returns the answer + trace.
    """
    trace_id = uuid.uuid4().hex
    steps: list[ToolResult] = []

    # ── Step 1: Retrieval ─────────────────────────────────
    retrieval = registry.get("retrieval")
    agent1 = retrieval.agent_factory()
    env1 = ToolEnvelope(
        trace_id=trace_id,
        callee="retrieval",
        intent="chat.retrieve",
        inputs={"query": req.user_text, "limit": 10},
    )
    r1 = await agent1.run(env1)
    steps.append(r1)
    context = r1.outputs.get("results", [])

    # ── Step 2: Weaver ────────────────────────────────────
    weaver = registry.get("weaver")
    agent2 = weaver.agent_factory()
    env2 = ToolEnvelope(
        trace_id=trace_id,
        callee="weaver",
        intent="chat.weave",
        inputs={"query": req.user_text, "context": context},
    )
    r2 = await agent2.run(env2)
    steps.append(r2)
    answer = r2.outputs.get("answer", "")
    citations = r2.outputs.get("citations", [])

    # ── Step 3: Verifier ──────────────────────────────────
    verifier = registry.get("verifier")
    agent3 = verifier.agent_factory()
    env3 = ToolEnvelope(
        trace_id=trace_id,
        callee="verifier",
        intent="chat.verify",
        inputs={"answer": answer, "context": context},
    )
    r3 = await agent3.run(env3)
    steps.append(r3)

    # ── Persist conversation turn ─────────────────────────
    turn_id = uuid.uuid4().hex
    insert_conversation_turn(turn_id, req.user_text, answer)

    return ChatResponse(
        answer=answer,
        citations=citations,
        trace_id=trace_id,
        steps=steps,
    )
