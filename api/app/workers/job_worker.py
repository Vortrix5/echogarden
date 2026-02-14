"""Continuous background job worker — asyncio task.

Phase 3: delegates ingest_blob jobs to the Active Orchestrator.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from app.capture.repo import claim_job, complete_job
from app.orchestrator.orchestrator import Orchestrator

logger = logging.getLogger("echogarden.worker")

_WORKER_SLEEP = 0.5  # seconds between polls when queue is empty
_orch = Orchestrator()


def _format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


async def _handle_ingest_blob(payload: dict) -> None:
    """Process a single ingest_blob job via the Orchestrator."""
    path: str = payload["path"]
    blob_id: str = payload["blob_id"]
    source_id: str = payload["source_id"]
    mime: str = payload.get("mime", "application/octet-stream")
    size_bytes: int = payload.get("size_bytes", 0)
    trace_id: str | None = payload.get("trace_id")
    fname = os.path.basename(path)

    from app.orchestrator.router import choose_pipeline
    pipeline = choose_pipeline(mime, path)

    logger.info(
        "[PROCESS] %s — mime=%s, %s, pipeline=%s, blob=%s",
        fname, mime, _format_size(size_bytes), pipeline.value, blob_id[:12],
    )

    result = await _orch.ingest_blob(
        blob_id=blob_id,
        source_id=source_id,
        path=path,
        mime=mime,
        size_bytes=size_bytes,
        trace_id=trace_id,
    )

    # Log each orchestrator step so the user can see every tool in the pipeline
    for i, step in enumerate(result.steps, 1):
        icon = "✓" if step.status == "ok" else "✗"
        out_keys = list(step.outputs.keys()) if step.outputs else []
        logger.info(
            "[STEP %d]  %s %s — %dms — outputs=%s%s",
            i,
            icon,
            step.tool_name,
            step.elapsed_ms,
            out_keys,
            f" error={step.error}" if step.error else "",
        )

    logger.info(
        "[DONE]    %s — pipeline=%s, steps=%d, memory_card=%s, trace=%s, status=%s",
        fname,
        result.pipeline,
        len(result.steps),
        (result.memory_id or "—")[:12],
        result.trace_id[:12],
        result.status,
    )


async def _handle_ingest_capture(payload: dict) -> None:
    """Process a browser capture job — generate text embedding for the captured text."""
    memory_id = payload.get("memory_id", "")
    text = payload.get("text", "")
    source_type = payload.get("source_type", "browser")
    card_type = payload.get("card_type", "browser_highlight")

    if not text or not text.strip():
        logger.info("[CAPTURE] Skipping empty text for memory=%s", memory_id[:12])
        return

    logger.info(
        "[CAPTURE] Embedding text for memory=%s type=%s (%d chars)",
        memory_id[:12], card_type, len(text),
    )

    # Run text embedding via the tool registry
    from app.core.tool_contracts import ToolEnvelope
    from app.core.tool_registry import registry

    entry = registry.get("text_embed")
    if entry is None:
        logger.warning("[CAPTURE] text_embed tool not registered — skipping")
        return

    agent = entry.agent_factory()
    envelope = ToolEnvelope(
        callee="text_embed",
        intent="capture.embed",
        inputs={"text": text, "memory_id": memory_id, "source_type": source_type},
        constraints={"timeout_ms": 120000},
    )
    result = await agent.run(envelope)

    if result.status.value == "ok":
        vector_ref = result.outputs.get("vector_ref", "")
        if vector_ref:
            from app.db import repo as db_repo
            db_repo.insert_embedding(memory_id, modality="text", vector_ref=vector_ref)
            logger.info("[CAPTURE] Embedding stored: %s for memory=%s", vector_ref[:30], memory_id[:12])
    else:
        logger.warning("[CAPTURE] text_embed failed for memory=%s: %s", memory_id[:12], result.error)


_JOB_HANDLERS = {
    "ingest_blob": _handle_ingest_blob,
    "ingest_capture": _handle_ingest_capture,
}


async def worker_loop() -> None:
    """Run forever: claim and process jobs from the queue."""
    logger.info("Job worker started (Phase 3 — Orchestrator)")
    jobs_processed = 0
    while True:
        try:
            job = await asyncio.to_thread(claim_job)
            if job is None:
                await asyncio.sleep(_WORKER_SLEEP)
                continue

            jobs_processed += 1
            job_id = job["job_id"]
            job_type = job["type"]
            payload = json.loads(job["payload_json"])

            logger.info(
                "[CLAIM]  Job #%d — id=%s type=%s",
                jobs_processed, job_id[:12], job_type,
            )

            handler = _JOB_HANDLERS.get(job_type)
            if handler is None:
                logger.warning("[SKIP]   Unknown job type: %s", job_type)
                await asyncio.to_thread(
                    complete_job, job_id, f"Unknown job type: {job_type}"
                )
                continue

            try:
                await handler(payload)
                await asyncio.to_thread(complete_job, job_id, None)
                logger.info("[OK]     Job %s completed successfully", job_id[:12])
            except Exception as exc:
                logger.exception("[FAIL]   Job %s failed: %s", job_id[:12], exc)
                await asyncio.to_thread(complete_job, job_id, str(exc))

        except Exception:
            logger.exception("Worker loop error")
            await asyncio.sleep(_WORKER_SLEEP)
