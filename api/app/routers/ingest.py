"""Router: Ingest — delegates to the Active Orchestrator."""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.orchestrator.models import StepResult
from app.orchestrator.orchestrator import Orchestrator

router = APIRouter(tags=["ingest"])
_orch = Orchestrator()


class IngestRequest(BaseModel):
    text: str


class IngestResponse(BaseModel):
    memory_id: str | None = None
    trace_id: str
    steps: list[StepResult] = Field(default_factory=list)
    status: str = "ok"


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest):
    """Ingest text via the Orchestrator pipeline.

    Creates an in-memory blob-like record and runs the doc_parse pipeline.
    """
    blob_id = uuid.uuid4().hex
    source_id = uuid.uuid4().hex
    trace_id = uuid.uuid4().hex

    result = await _orch.ingest_blob(
        blob_id=blob_id,
        source_id=source_id,
        path="<inline>",
        mime="text/plain",
        size_bytes=len(req.text.encode()),
        trace_id=trace_id,
    )

    return IngestResponse(
        memory_id=result.memory_id,
        trace_id=result.trace_id,
        steps=result.steps,
        status=result.status,
    )
