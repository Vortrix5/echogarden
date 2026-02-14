"""Router: capture status and job listing."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.capture.config import EG_MAX_FILE_MB, EG_POLL_INTERVAL, EG_WATCH_ROOTS
from app.capture.repo import count_jobs, list_jobs, count_file_states, count_blobs

router = APIRouter(prefix="/capture", tags=["capture"])


class CaptureStatus(BaseModel):
    watch_roots: list[str]
    poll_interval_s: float
    max_file_mb: float
    tracked_files: int
    total_blobs: int
    jobs_queued: int
    jobs_running: int
    jobs_done: int
    jobs_error: int


@router.get("/status", response_model=CaptureStatus)
async def capture_status():
    return CaptureStatus(
        watch_roots=EG_WATCH_ROOTS,
        poll_interval_s=EG_POLL_INTERVAL,
        max_file_mb=EG_MAX_FILE_MB,
        tracked_files=count_file_states(),
        total_blobs=count_blobs(),
        jobs_queued=count_jobs("queued"),
        jobs_running=count_jobs("running"),
        jobs_done=count_jobs("done"),
        jobs_error=count_jobs("error"),
    )


@router.get("/jobs")
async def get_jobs(
    status: str | None = Query(None, description="Filter by status: queued|running|done|error"),
    limit: int = Query(50, ge=1, le=500),
):
    return list_jobs(status=status, limit=limit)
