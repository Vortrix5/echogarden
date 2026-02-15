"""Active Orchestrator — deterministic, traceable pipeline execution.

Provides two entry-points:
    Orchestrator.ingest_blob(...)   — file ingestion pipeline
    Orchestrator.chat(...)          — chat pipeline
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

from app.core.tool_contracts import ToolEnvelope, ToolResult, ToolStatus
from app.core.tool_registry import registry
from app.db import repo as db_repo
from app.orchestrator.llm import (
    llm_available,
    verify_with_llm,
    weave_with_llm,
)
from app.orchestrator.models import (
    ChatResult,
    IngestResult,
    PipelineType,
    StepResult,
)
from app.orchestrator.router import (
    build_chat_steps,
    build_ingest_steps,
    choose_pipeline,
    is_image_pipeline,
)
from app.retrieval.models import RetrieveRequest
from app.retrieval.service import hybrid_retrieve

logger = logging.getLogger("echogarden.orchestrator")

# Maximum input length for the chat security check.
_MAX_CHAT_INPUT_LEN = 50_000


# ─────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex


def _read_text_content(path: str, max_bytes: int = 20 * 1024 * 1024) -> str:
    """Read text content from a local file.

    Raises FileNotFoundError / OSError on failure so the caller can
    abort the pipeline instead of ingesting an error message.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(max_bytes)


# ─────────────────────────────────────────────────────────
#  Orchestrator
# ─────────────────────────────────────────────────────────

class Orchestrator:
    """Active Orchestrator — plans, dispatches, and traces tool pipelines."""

    # ── Ingest blob ───────────────────────────────────────
    async def ingest_blob(
        self,
        *,
        blob_id: str,
        source_id: str,
        path: str,
        mime: str,
        size_bytes: int = 0,
        trace_id: str | None = None,
    ) -> IngestResult:
        trace_id = trace_id or _new_id()

        # Idempotency: check if a memory card already exists for this blob+trace
        existing = db_repo.find_memory_card_by_blob(blob_id)
        if existing:
            logger.info(
                "[ORCH]   trace=%s — idempotent skip, card already exists for blob=%s",
                trace_id[:12], blob_id[:12],
            )
            return IngestResult(
                trace_id=trace_id,
                pipeline="skip",
                memory_id=existing,
                status="idempotent_skip",
            )

        # Choose pipeline
        pipeline = choose_pipeline(mime, path)
        logger.info(
            "[ORCH]   trace=%s — pipeline=%s for %s (%s)",
            trace_id[:12], pipeline.value, os.path.basename(path), mime,
        )

        # Create exec_trace
        db_repo.insert_exec_trace(trace_id, metadata={
            "blob_id": blob_id,
            "source_id": source_id,
            "path": path,
            "mime": mime,
            "pipeline": pipeline.value,
        })

        # ── Image: parallel OCR + VisionEmbed ─────────────
        if is_image_pipeline(pipeline):
            return await self._ingest_image(
                trace_id=trace_id,
                blob_id=blob_id,
                source_id=source_id,
                path=path,
                mime=mime,
                size_bytes=size_bytes,
            )

        # ── Non-image: sequential steps (doc_parse / asr) ─
        return await self._ingest_sequential(
            trace_id=trace_id,
            pipeline=pipeline,
            blob_id=blob_id,
            source_id=source_id,
            path=path,
            mime=mime,
            size_bytes=size_bytes,
        )

    # ── Sequential pipeline (doc_parse, asr) ──────────────
    async def _ingest_sequential(
        self,
        *,
        trace_id: str,
        pipeline: PipelineType,
        blob_id: str,
        source_id: str,
        path: str,
        mime: str,
        size_bytes: int,
    ) -> IngestResult:
        # Build steps
        steps_def = build_ingest_steps(
            pipeline, path=path, blob_id=blob_id,
            source_id=source_id, mime=mime,
        )

        # If doc_parse pipeline, pre-read text content for the first step
        content_text = ""
        if pipeline == PipelineType.doc_parse:
            try:
                content_text = _read_text_content(path)
            except OSError as exc:
                logger.error(
                    "[ORCH]   trace=%s — cannot read file %s: %s",
                    trace_id[:12], path, exc,
                )
                db_repo.finish_exec_trace(trace_id, "error")
                return IngestResult(
                    trace_id=trace_id,
                    pipeline=pipeline.value,
                    status="error",
                    steps=[StepResult(
                        tool_name="read_file",
                        call_id=_new_id(),
                        exec_node_id=_new_id(),
                        status="error",
                        error=str(exc),
                        elapsed_ms=0,
                    )],
                )
            steps_def[0].inputs["text"] = content_text

        # Generate memory_id early so downstream tools (text_embed, graph_builder) can reference it
        memory_id = _new_id()

        # Execute steps sequentially
        step_results: list[StepResult] = []
        prev_exec_node_id: str | None = None
        extracted_text = content_text  # flows through pipeline
        summary = ""
        entities: list[dict] = []
        tags: list[str] = []
        actions: list[dict] = []

        for step_def in steps_def:
            # Wire inputs from previous step outputs
            inputs = dict(step_def.inputs)

            if step_def.tool_name == "summarizer":
                inputs["content_text"] = extracted_text
                inputs["title"] = os.path.basename(path)

            if step_def.tool_name == "extractor":
                inputs["content_text"] = extracted_text
                inputs["title"] = os.path.basename(path)

            if step_def.tool_name == "text_embed" and extracted_text:
                inputs["text"] = extracted_text
                inputs["memory_id"] = memory_id

            if step_def.tool_name == "graph_builder":
                inputs["entities"] = entities
                inputs["memory_id"] = memory_id
                inputs["source"] = {
                    "blob_id": blob_id,
                    "source_id": source_id,
                    "path": path,
                    "mime": mime,
                    "trace_id": trace_id,
                }

            sr = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name=step_def.tool_name,
                intent=step_def.intent,
                inputs=inputs,
                timeout_ms=step_def.timeout_ms,
                prev_exec_node_id=prev_exec_node_id,
            )
            step_results.append(sr)
            prev_exec_node_id = sr.exec_node_id

            if step_def.tool_name in ("doc_parse", "ocr", "asr"):
                extracted_text = sr.outputs.get("content_text") or sr.outputs.get("text", extracted_text)

            if step_def.tool_name == "summarizer" and sr.status == "ok":
                summary = sr.outputs.get("summary", "")

            if step_def.tool_name == "extractor" and sr.status == "ok":
                entities = sr.outputs.get("entities", [])
                tags = sr.outputs.get("tags", [])
                actions = sr.outputs.get("actions", [])

            if sr.status != "ok":
                logger.warning(
                    "[ORCH]   trace=%s — step %s failed: %s",
                    trace_id[:12], step_def.tool_name, sr.error,
                )
                # Non-fatal for summarizer/extractor — continue pipeline
                if step_def.tool_name not in ("summarizer", "extractor"):
                    db_repo.finish_exec_trace(trace_id, "error")
                    return IngestResult(
                        trace_id=trace_id,
                        pipeline=pipeline.value,
                        steps=step_results,
                        status="error",
                    )

        # Fallback summary if LLM failed
        if not summary:
            summary = (extracted_text or "")[:400]
            # Try to cut at sentence boundary
            for sep in (". ", ".\n"):
                idx = summary.rfind(sep)
                if idx > 30:
                    summary = summary[:idx + 1].strip()
                    break

        # Get text embedding vector_ref if available
        text_vector_ref = ""
        for sr in step_results:
            if sr.tool_name == "text_embed" and sr.status == "ok":
                text_vector_ref = sr.outputs.get("vector_ref", "")

        metadata_json = {
            "blob_id": blob_id,
            "source_id": source_id,
            "file_path": path,
            "mime": mime,
            "size_bytes": size_bytes,
            "trace_id": trace_id,
            "pipeline": pipeline.value,
            "source_type": "file_capture",
            "text_vector_ref": text_vector_ref or None,
            "entities": entities,
            "tags": tags,
            "actions": actions,
            "embedding_refs": {"text": text_vector_ref or None},
        }
        db_repo.insert_memory_card(
            memory_id=memory_id,
            card_type="file_capture",
            summary=summary,
            content_text=extracted_text or None,
            metadata_json=metadata_json,
        )

        # Persist EMBEDDING row for text modality
        if text_vector_ref:
            db_repo.insert_embedding(memory_id, modality="text", vector_ref=text_vector_ref)

        logger.info(
            "[ORCH]   trace=%s — memory_card=%s created (summary=%d chars, entities=%d)",
            trace_id[:12], memory_id[:12], len(summary), len(entities),
        )

        try:
            self._upsert_graph(memory_id, summary, step_results, entities)
        except Exception:
            logger.exception("[ORCH]   trace=%s — graph upsert failed (non-fatal)", trace_id[:12])

        db_repo.finish_exec_trace(trace_id, "done")

        return IngestResult(
            trace_id=trace_id,
            pipeline=pipeline.value,
            memory_id=memory_id,
            steps=step_results,
            status="ok",
        )

    # ── Image pipeline: parallel OCR + VisionEmbed ────────
    async def _ingest_image(
        self,
        *,
        trace_id: str,
        blob_id: str,
        source_id: str,
        path: str,
        mime: str,
        size_bytes: int,
    ) -> IngestResult:
        from app.capture.config import EG_MAX_FILE_BYTES
        from app.tools.ocr_quality import is_meaningful_ocr

        fname = os.path.basename(path)
        step_results: list[StepResult] = []
        oversized = size_bytes > EG_MAX_FILE_BYTES

        # ── Oversized guard ───────────────────────────────
        if oversized:
            logger.info(
                "[ROUTE]  image %s oversized (%d bytes) — placeholder only",
                fname, size_bytes,
            )
            memory_id = _new_id()
            db_repo.insert_memory_card(
                memory_id=memory_id,
                card_type="file_capture_placeholder",
                summary=(
                    f"Image file captured; oversized — parsing skipped.\n"
                    f"File: {fname} | Size: {size_bytes} bytes | MIME: {mime}"
                ),
                metadata={
                    "blob_id": blob_id,
                    "source_id": source_id,
                    "file_path": path,
                    "mime": mime,
                    "size_bytes": size_bytes,
                    "trace_id": trace_id,
                    "pipeline": "ocr",
                    "skipped_reason": "oversized",
                },
            )
            db_repo.finish_exec_trace(trace_id, "done")
            return IngestResult(
                trace_id=trace_id,
                pipeline="ocr",
                memory_id=memory_id,
                status="ok",
            )

        # ── Parallel branch: OCR + VisionEmbed ────────────
        # Generate memory_id early so text_embed / graph_builder get the real id
        memory_id = _new_id()
        logger.info(
            "[ROUTE]  image detected → parallel branches: OCR + VisionEmbed for %s",
            fname,
        )

        async def _run_ocr() -> StepResult:
            return await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="ocr",
                intent="ingest.ocr",
                inputs={"image_path": path},
                timeout_ms=30000,
                prev_exec_node_id=None,  # root-level, no predecessor
            )

        async def _run_vision_embed() -> StepResult:
            return await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="vision_embed",
                intent="ingest.vision_embed",
                inputs={
                    "image_path": path,
                    "blob_id": blob_id,
                    "memory_id": memory_id,
                    "mime": mime,
                    "source_type": "file",
                },
                timeout_ms=300000,
                prev_exec_node_id=None,  # root-level, no predecessor
            )

        # Launch both in parallel — neither depends on the other
        sr_ocr, sr_vision = await asyncio.gather(
            _run_ocr(),
            _run_vision_embed(),
            return_exceptions=False,
        )
        step_results.extend([sr_ocr, sr_vision])

        # ── Extract OCR output (structured) ───────────────
        ocr_text = ""
        ocr_status = "failed"
        ocr_error: str | None = None
        ocr_avg_confidence: float | None = None

        if sr_ocr.status == "ok":
            ocr_text = sr_ocr.outputs.get("text", "")
            ocr_status = sr_ocr.outputs.get("status", "success")
            ocr_error = sr_ocr.outputs.get("error")
            ocr_avg_confidence = sr_ocr.outputs.get("avg_confidence")
        else:
            ocr_status = "failed"
            ocr_error = sr_ocr.error or "OCR tool dispatch failed"

        vision_vector_ref = ""
        if sr_vision.status == "ok":
            vision_vector_ref = sr_vision.outputs.get("vector_ref", "")

        # ── Decide base_text: OCR vs caption ──────────────
        ocr_meaningful = is_meaningful_ocr(
            ocr_text,
            avg_confidence=ocr_avg_confidence,
        )

        base_text = ""
        base_text_source = ""
        caption_text = ""
        caption_model = ""
        sr_caption = None

        if ocr_meaningful:
            base_text = ocr_text
            base_text_source = "ocr"
            logger.info(
                "[IMAGE]  ocr_status=%s ocr_len=%d -> using ocr",
                ocr_status, len(ocr_text),
            )
        elif ocr_text and len(ocr_text.strip()) >= 20:
            # OCR produced some text but failed the strict quality check.
            # For diagrams / technical images this is still far more useful
            # than a generic CLIP caption, so prefer it.
            base_text = ocr_text
            base_text_source = "ocr"
            logger.info(
                "[IMAGE]  ocr_status=%s ocr_len=%d quality=low -> still using ocr (better than caption for diagrams)",
                ocr_status, len(ocr_text),
            )
        else:
            # ── Caption fallback ──────────────────────────
            logger.info(
                "[IMAGE]  ocr_status=%s ocr_len=%d -> using caption",
                ocr_status, len(ocr_text),
            )
            sr_caption = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="image_caption",
                intent="ingest.caption",
                inputs={"image_path": path},
                timeout_ms=60000,
                prev_exec_node_id=sr_ocr.exec_node_id,
            )
            step_results.append(sr_caption)

            if sr_caption.status == "ok":
                caption_text = sr_caption.outputs.get("caption", "")
                caption_model = sr_caption.outputs.get("model", "")
                if caption_text:
                    base_text = caption_text
                    base_text_source = "caption"
            else:
                logger.warning(
                    "[ORCH]   trace=%s — caption also failed, using filename fallback",
                    trace_id[:12],
                )
                base_text = f"Image: {fname}"
                base_text_source = "filename"

        logger.info(
            "[ORCH]   trace=%s — OCR %s (%d chars), VisionEmbed %s (ref=%s), base_text_source=%s",
            trace_id[:12],
            ocr_status, len(ocr_text),
            sr_vision.status, vision_vector_ref[:20] if vision_vector_ref else "—",
            base_text_source,
        )

        # ── Sequential: Summarizer + Extractor + TextEmbed (if base_text) ──
        text_vector_ref = ""
        summary = ""
        entities: list[dict] = []
        tags: list[str] = []
        actions: list[dict] = []

        if base_text.strip():
            # Decide which LLM agents to run based on text source:
            #  - OCR text: run summarizer + extractor (full pipeline)
            #  - BLIP caption: skip summarizer (caption IS the summary),
            #    but run extractor to get entities/tags for the graph
            #  - CLIP/heuristic caption: too short for LLM, extract from
            #    CLIP subjects directly
            is_ocr = base_text_source == "ocr"
            is_blip = (base_text_source == "caption"
                       and caption_model == "blip")

            if is_ocr:
                # ── Summarizer (only for OCR text) ──
                sr_summarizer = await self._dispatch_tool(
                    trace_id=trace_id,
                    tool_name="summarizer",
                    intent="ingest.summarize",
                    inputs={"content_text": base_text, "title": fname},
                    timeout_ms=180000,
                    prev_exec_node_id=sr_ocr.exec_node_id,
                )
                step_results.append(sr_summarizer)
                if sr_summarizer.status == "ok":
                    summary = sr_summarizer.outputs.get("summary", "")

            if is_ocr or is_blip:
                # ── Extractor (OCR and BLIP captions) ──
                sr_extractor = await self._dispatch_tool(
                    trace_id=trace_id,
                    tool_name="extractor",
                    intent="ingest.extract",
                    inputs={"content_text": base_text, "title": fname},
                    timeout_ms=180000,
                    prev_exec_node_id=sr_ocr.exec_node_id,
                )
                step_results.append(sr_extractor)
                if sr_extractor.status == "ok":
                    entities = sr_extractor.outputs.get("entities", [])
                    tags = sr_extractor.outputs.get("tags", [])
                    actions = sr_extractor.outputs.get("actions", [])

                if is_blip:
                    # BLIP caption IS the summary — no need for summarizer
                    summary = base_text
                    logger.info(
                        "[ORCH]   trace=%s — BLIP caption used as summary, "
                        "extractor extracted %d entities, %d tags",
                        trace_id[:12], len(entities), len(tags),
                    )
            else:
                # CLIP / heuristic caption: too short for LLM
                summary = base_text

                # Extract entities from CLIP subjects (no LLM needed)
                if sr_caption and sr_caption.status == "ok":
                    clip_subjects = sr_caption.outputs.get("subjects", [])
                    for subj in clip_subjects:
                        entities.append({
                            "name": subj["name"],
                            "type": "Topic",
                            "confidence": subj.get("confidence", 0.0),
                        })
                    clip_tags = sr_caption.outputs.get("tags", [])
                    if clip_tags:
                        tags = clip_tags

                logger.info(
                    "[ORCH]   trace=%s — caption-sourced (model=%s), "
                    "extracted %d entities from CLIP subjects, %d tags",
                    trace_id[:12], caption_model, len(entities), len(tags),
                )

            # ── TextEmbed (always — embeds caption or OCR text) ──
            sr_text_embed = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="text_embed",
                intent="ingest.embed",
                inputs={"text": base_text, "memory_id": memory_id, "source_type": "file"},
                timeout_ms=120000,
                prev_exec_node_id=sr_ocr.exec_node_id,
            )
            step_results.append(sr_text_embed)
            if sr_text_embed.status == "ok":
                text_vector_ref = sr_text_embed.outputs.get("vector_ref", "")
        else:
            logger.info(
                "[ORCH]   trace=%s — skipping summarizer/extractor/text_embed (no base_text)",
                trace_id[:12],
            )

        # ── Sequential: GraphBuilder (only if entities extracted) ──
        if entities:
            prev_node = step_results[-1].exec_node_id
            sr_graph = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="graph_builder",
                intent="ingest.graph",
                inputs={
                    "entities": entities,
                    "memory_id": memory_id,
                    "source": {
                        "blob_id": blob_id,
                        "source_id": source_id,
                        "path": path,
                        "mime": mime,
                        "trace_id": trace_id,
                    },
                },
                timeout_ms=10000,
                prev_exec_node_id=prev_node,
            )
            step_results.append(sr_graph)
        else:
            logger.info(
                "[ORCH]   trace=%s — skipping graph_builder (no entities)",
                trace_id[:12],
            )

        # Fallback summary — never store OCR errors as summary
        if not summary:
            if base_text and base_text.strip():
                summary = base_text[:400]
                # Try to cut at sentence boundary
                for sep in (". ", ".\n"):
                    idx = summary.rfind(sep)
                    if idx > 30:
                        summary = summary[:idx + 1].strip()
                        break
            else:
                summary = f"Image: {fname}"

        card_type = "file_capture"

        # Determine overall status
        any_ok = sr_ocr.status == "ok" or sr_vision.status == "ok"
        overall_status = "ok" if any_ok else "error"

        metadata_json = {
            "blob_id": blob_id,
            "source_id": source_id,
            "file_path": path,
            "mime": mime,
            "size_bytes": size_bytes,
            "trace_id": trace_id,
            "pipeline": "ocr",
            "source_type": "file_capture",
            "base_text_source": base_text_source,
            "ocr_status": ocr_status,
            "ocr_error": ocr_error,
            "ocr_text_len": len(ocr_text),
            "ocr_avg_confidence": ocr_avg_confidence,
            "caption_text": caption_text or None,
            "caption_model": caption_model or None,
            "vision_status": sr_vision.status,
            "entities": entities,
            "tags": tags,
            "actions": actions,
            "embedding_refs": {
                "text": text_vector_ref or None,
                "vision": vision_vector_ref or None,
            },
        }

        # content_text = base_text (OCR or caption), never OCR error messages
        db_repo.insert_memory_card(
            memory_id=memory_id,
            card_type=card_type,
            summary=summary,
            content_text=base_text if base_text.strip() else None,
            metadata_json=metadata_json,
        )
        logger.info(
            "[ORCH]   trace=%s — memory_card=%s created "
            "(base_text_source=%s, ocr=%s, vision=%s, entities=%d, "
            "embedding_refs: text=%s vision=%s)",
            trace_id[:12], memory_id[:12],
            base_text_source, ocr_status, sr_vision.status,
            len(entities),
            "present" if text_vector_ref else "none",
            "present" if vision_vector_ref else "none",
        )

        # Persist EMBEDDING rows for each modality
        if text_vector_ref:
            db_repo.insert_embedding(memory_id, modality="text", vector_ref=text_vector_ref)
        if vision_vector_ref:
            db_repo.insert_embedding(memory_id, modality="vision", vector_ref=vision_vector_ref)

        # Best-effort graph upsert
        try:
            self._upsert_graph(memory_id, summary, step_results, entities)
        except Exception:
            logger.exception("[ORCH]   trace=%s — graph upsert failed (non-fatal)", trace_id[:12])

        db_repo.finish_exec_trace(trace_id, overall_status if overall_status == "error" else "done")

        return IngestResult(
            trace_id=trace_id,
            pipeline="ocr",
            memory_id=memory_id,
            steps=step_results,
            status=overall_status,
        )

    # ── Chat ──────────────────────────────────────────────
    async def chat(
        self,
        user_text: str,
        *,
        trace_id: str | None = None,
        top_k: int = 8,
        use_graph: bool = True,
        hops: int = 1,
    ) -> ChatResult:
        """Phase 7 grounded Q&A: retrieval → weaver → verifier → persist."""
        trace_id = trace_id or _new_id()

        db_repo.insert_exec_trace(trace_id, metadata={
            "pipeline": "chat",
            "user_text": user_text[:200],
        })

        step_results: list[StepResult] = []
        prev_exec_node_id: str | None = None

        # ── Step 0: Security check ────────────────────────
        sec_status, sec_reason = self._security_check(user_text)
        if sec_status != "pass":
            logger.warning("[ORCH]   trace=%s — security check failed: %s", trace_id[:12], sec_reason)
            db_repo.finish_exec_trace(trace_id, "rejected")
            return ChatResult(
                trace_id=trace_id,
                answer=f"Request rejected: {sec_reason}",
                status="rejected",
            )

        # ── Step 1: Retrieval (Phase 5 hybrid) ────────────
        retrieve_req = RetrieveRequest(
            query=user_text,
            top_k=top_k * 3,
            use_graph=use_graph,
            hops=hops,
        )
        retrieve_resp = await hybrid_retrieve(retrieve_req)
        raw_results = [r.dict() for r in retrieve_resp.results]

        # Record retrieval as a traced tool dispatch
        sr_retrieval = await self._dispatch_tool(
            trace_id=trace_id,
            tool_name="retrieval",
            intent="chat.retrieve",
            inputs={"query": user_text, "limit": top_k * 3, "hops": hops,
                    "_llm_override": {"results": raw_results}},
            timeout_ms=15000,
            prev_exec_node_id=prev_exec_node_id,
        )
        step_results.append(sr_retrieval)
        prev_exec_node_id = sr_retrieval.exec_node_id

        # ── Build evidence with content_text ──────────────
        evidence = self._build_evidence(raw_results, top_k)

        # ── Step 2: Weave ─────────────────────────────────
        use_llm = await llm_available()
        if use_llm:
            logger.info("[ORCH]   trace=%s — using LLM for weave", trace_id[:12])
            llm_result = await weave_with_llm(user_text, evidence)
            sr_weave = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="weaver",
                intent="chat.weave",
                inputs={
                    "question": user_text,
                    "evidence": evidence,
                    "_llm_override": llm_result,
                },
                timeout_ms=180000,
                prev_exec_node_id=prev_exec_node_id,
            )
        else:
            sr_weave = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="weaver",
                intent="chat.weave",
                inputs={"question": user_text, "evidence": evidence},
                timeout_ms=30000,
                prev_exec_node_id=prev_exec_node_id,
            )
        step_results.append(sr_weave)
        prev_exec_node_id = sr_weave.exec_node_id
        answer = sr_weave.outputs.get("answer", "")
        citations = sr_weave.outputs.get("citations", [])

        # ── Step 3: Verify ────────────────────────────────
        if use_llm:
            verify_result = await verify_with_llm(user_text, answer, evidence)
            sr_verify = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="verifier",
                intent="chat.verify",
                inputs={
                    "question": user_text,
                    "answer": answer,
                    "evidence": evidence,
                    "citations": citations,
                    "_llm_override": verify_result,
                },
                timeout_ms=60000,
                prev_exec_node_id=prev_exec_node_id,
            )
        else:
            sr_verify = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="verifier",
                intent="chat.verify",
                inputs={
                    "question": user_text,
                    "answer": answer,
                    "evidence": evidence,
                    "citations": citations,
                },
                timeout_ms=15000,
                prev_exec_node_id=prev_exec_node_id,
            )
        step_results.append(sr_verify)

        verdict = sr_verify.outputs.get("verdict", "pass")
        revised_answer = sr_verify.outputs.get("revised_answer", "")
        issues = sr_verify.outputs.get("issues", [])

        # Apply revision if verdict says so
        if verdict == "revise" and revised_answer:
            answer = revised_answer
        elif verdict == "abstain":
            answer = (
                "I don't have enough evidence to answer this question reliably. "
                + (f"Issues: {'; '.join(issues)}" if issues else "")
            ).strip()

        # Enrich citations with source_type + created_at from evidence
        ev_map = {e["memory_id"]: e for e in evidence if "memory_id" in e}
        enriched_citations = []
        for c in citations:
            mid = c.get("memory_id", "")
            ev = ev_map.get(mid, {})
            enriched_citations.append({
                "memory_id": mid,
                "quote": c.get("quote", ""),
                "source_type": ev.get("source_type", ""),
                "created_at": ev.get("created_at", ""),
            })

        # Build evidence response items
        evidence_out = []
        for ev in evidence:
            evidence_out.append({
                "memory_id": ev.get("memory_id", ""),
                "summary": ev.get("summary", ""),
                "snippet": (ev.get("content_text") or ev.get("summary", ""))[:300],
                "score": ev.get("score", 0.0),
                "reasons": ev.get("reasons", []),
            })

        # ── Step 4: Persist conversation turn + citations ─
        turn_id = _new_id()
        db_repo.insert_conversation_turn(
            turn_id, user_text, answer, trace_id=trace_id, verdict=verdict,
        )
        db_repo.insert_chat_citations(turn_id, enriched_citations)

        db_repo.finish_exec_trace(trace_id, "done")

        return ChatResult(
            trace_id=trace_id,
            answer=answer,
            citations=enriched_citations,
            verdict=verdict,
            evidence=evidence_out,
            steps=step_results,
            status="ok",
        )

    # ── Evidence builder ──────────────────────────────────
    def _build_evidence(self, raw_results: list[dict], top_k: int) -> list[dict]:
        """Fetch content_text for retrieved cards and format as evidence."""
        # Collect memory_ids from retrieval results
        memory_ids = [r.get("memory_id") for r in raw_results if r.get("memory_id")]
        if not memory_ids:
            return []

        # Fetch full card rows to get content_text + metadata
        cards_by_id = {}
        try:
            card_rows = db_repo.fetch_memory_cards_by_ids(memory_ids[:top_k * 2])
            for row in card_rows:
                cards_by_id[row["memory_id"]] = row
        except Exception:
            logger.debug("Failed to fetch memory cards for evidence", exc_info=True)

        evidence: list[dict] = []
        for r in raw_results[:top_k]:
            mid = r.get("memory_id", "")
            card = cards_by_id.get(mid, {})

            # Parse metadata_json
            meta = {}
            raw_meta = card.get("metadata_json") or card.get("metadata")
            if raw_meta:
                if isinstance(raw_meta, str):
                    try:
                        meta = json.loads(raw_meta)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(raw_meta, dict):
                    meta = raw_meta

            content_text = card.get("content_text") or ""
            summary = r.get("summary") or card.get("summary") or ""
            snippet = (content_text[:800] if content_text else summary[:800])

            evidence.append({
                "memory_id": mid,
                "summary": summary,
                "content_text": snippet,
                "source_type": meta.get("source_type", card.get("type", "")),
                "created_at": card.get("created_at", ""),
                "score": r.get("final_score", r.get("score", 0.0)),
                "reasons": r.get("reasons") if isinstance(r.get("reasons"), list)
                           else ([r.get("reason")] if r.get("reason") else []),
            })

        return evidence

    # ─────────────────────────────────────────────────────
    #  Internal helpers
    # ─────────────────────────────────────────────────────

    async def _dispatch_tool(
        self,
        *,
        trace_id: str,
        tool_name: str,
        intent: str,
        inputs: dict[str, Any],
        timeout_ms: int = 8000,
        prev_exec_node_id: str | None = None,
    ) -> StepResult:
        """Dispatch a single tool call through the registry and persist trace."""
        entry = registry.get(tool_name)
        if entry is None:
            logger.error("[ORCH]   Tool '%s' not found in registry", tool_name)
            return StepResult(
                tool_name=tool_name,
                call_id="",
                exec_node_id="",
                status="error",
                error=f"Tool '{tool_name}' not registered",
            )

        logger.info(
            "[ORCH]   trace=%s — dispatching %s (intent=%s)",
            trace_id[:12], tool_name, intent,
        )

        agent = entry.agent_factory()
        envelope = ToolEnvelope(
            trace_id=trace_id,
            callee=tool_name,
            intent=intent,
            inputs=inputs,
            constraints={"timeout_ms": timeout_ms},  # type: ignore[arg-type]
        )

        result: ToolResult = await agent.run(envelope)

        # Extract call_id and exec_node_id from the recorded rows.
        # BasePassiveAgent.run() already persisted TOOL_CALL and EXEC_NODE.
        # We retrieve the latest for this trace.
        call_id = result.span_id  # span_id is unique per call
        exec_node_id = call_id  # simplified mapping

        # Look up the actual exec_node_id from DB
        node_info = db_repo.get_latest_exec_node_for_call(tool_name, trace_id)
        if node_info:
            call_id = node_info["call_id"]
            exec_node_id = node_info["exec_node_id"]

        # Record exec_edge if there's a predecessor
        if prev_exec_node_id and exec_node_id:
            db_repo.insert_exec_edge(prev_exec_node_id, exec_node_id, condition="sequential")

        # Update exec_node with trace_id
        if exec_node_id and node_info:
            db_repo.update_exec_node_trace(exec_node_id, trace_id)

        logger.info(
            "[ORCH]   trace=%s — %s finished status=%s elapsed=%dms",
            trace_id[:12], tool_name, result.status.value, result.elapsed_ms,
        )

        return StepResult(
            tool_name=tool_name,
            call_id=call_id,
            exec_node_id=exec_node_id,
            status=result.status.value,
            outputs=result.outputs,
            elapsed_ms=result.elapsed_ms,
            error=result.error.message if result.error else None,
        )

    def _security_check(self, user_text: str) -> tuple[str, str]:
        """Simple heuristic security check for chat input."""
        if len(user_text) > _MAX_CHAT_INPUT_LEN:
            return "fail", f"Input too long ({len(user_text)} chars, max {_MAX_CHAT_INPUT_LEN})"
        # Check for binary content (null bytes)
        if "\x00" in user_text:
            return "fail", "Binary content detected"
        return "pass", ""

    def _upsert_graph(
        self,
        memory_id: str,
        summary: str,
        step_results: list[StepResult],
        entities: list[dict] | None = None,
    ) -> None:
        """Best-effort graph upsert from graph_builder output."""
        try:
            from app.graph.models import GraphEdgeIn, GraphNodeIn
            from app.graph.service import GraphService

            graph = GraphService()

            # Memory card node
            mem_node = GraphNodeIn(
                node_id=f"mem:{memory_id}",
                node_type="MemoryCard",
                props={"summary": summary[:200]},
            )

            # Collect entity nodes/edges from graph_builder step
            entity_nodes: list[GraphNodeIn] = []
            graph_edges: list[GraphEdgeIn] = []

            for sr in step_results:
                if sr.tool_name == "graph_builder" and sr.status == "ok":
                    for n in sr.outputs.get("nodes", []):
                        entity_nodes.append(GraphNodeIn(**n))
                    for e in sr.outputs.get("edges", []):
                        edge_data = dict(e)
                        # Replace placeholder or any mem: prefix with real memory_id
                        fid = edge_data.get("from_node_id", "")
                        if fid.startswith("mem:"):
                            edge_data["from_node_id"] = f"mem:{memory_id}"
                        # Recalculate edge_id with real memory_id
                        import hashlib as _hl
                        edge_data["edge_id"] = _hl.sha1(
                            f"{edge_data['from_node_id']}|{edge_data.get('edge_type','')}|{edge_data.get('to_node_id','')}".encode()
                        ).hexdigest()[:32]
                        prov = edge_data.get("provenance", {})
                        if not prov.get("tool_call_id"):
                            prov["tool_call_id"] = sr.call_id
                        edge_data["provenance"] = prov
                        graph_edges.append(GraphEdgeIn(**edge_data))

            graph.upsert_nodes([mem_node] + entity_nodes)
            if graph_edges:
                graph.upsert_edges(graph_edges)

        except Exception:
            logger.debug("Graph service not available or failed", exc_info=True)
