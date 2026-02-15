"""Phase 5 — POST /retrieve   hybrid retrieval endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.retrieval.models import RetrieveRequest, RetrieveResponse
from app.retrieval.service import hybrid_retrieve

logger = logging.getLogger("echogarden.routers.retrieve")

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(body: RetrieveRequest) -> RetrieveResponse:
    """Hybrid retrieval: FTS + semantic + graph expand + recency + source boost.

    Returns top_k memory cards ranked by merged score with explainability.
    """
    return await hybrid_retrieve(body)
