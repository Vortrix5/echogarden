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

logger = logging.getLogger("echogarden.orchestrator")

# Maximum input length for the chat security check.
_MAX_CHAT_INPUT_LEN = 50_000


# ─────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex


def _read_text_content(path: str, max_bytes: int = 20 * 1024 * 1024) -> str:
    """Best-effort read of text content from a local file."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_bytes)
    except Exception as exc:
        return f"[Error reading file: {exc}]"


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
            content_text = _read_text_content(path)
            steps_def[0].inputs["text"] = content_text

        # Execute steps sequentially
        step_results: list[StepResult] = []
        prev_exec_node_id: str | None = None
        extracted_text = content_text  # flows through pipeline

        for step_def in steps_def:
            # Wire inputs from previous step outputs
            inputs = dict(step_def.inputs)

            if step_def.tool_name == "text_embed" and extracted_text:
                inputs["text"] = extracted_text

            if step_def.tool_name == "graph_builder":
                inputs["content_text"] = extracted_text
                if "memory_id" not in inputs:
                    inputs["memory_id"] = ""

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

            if sr.status != "ok":
                logger.warning(
                    "[ORCH]   trace=%s — step %s failed: %s",
                    trace_id[:12], step_def.tool_name, sr.error,
                )
                db_repo.finish_exec_trace(trace_id, "error")
                return IngestResult(
                    trace_id=trace_id,
                    pipeline=pipeline.value,
                    steps=step_results,
                    status="error",
                )

        # Commit memory card
        memory_id = _new_id()
        summary = (extracted_text or "")[:500]
        metadata = {
            "blob_id": blob_id,
            "source_id": source_id,
            "file_path": path,
            "mime": mime,
            "size_bytes": size_bytes,
            "trace_id": trace_id,
            "pipeline": pipeline.value,
        }
        db_repo.insert_memory_card(
            memory_id=memory_id,
            card_type="file_capture",
            summary=summary,
            metadata=metadata,
        )
        logger.info(
            "[ORCH]   trace=%s — memory_card=%s created",
            trace_id[:12], memory_id[:12],
        )

        try:
            self._upsert_graph(memory_id, summary, step_results)
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
                inputs={"image_path": path, "blob_id": blob_id, "mime": mime},
                timeout_ms=15000,
                prev_exec_node_id=None,  # root-level, no predecessor
            )

        # Launch both in parallel — neither depends on the other
        sr_ocr, sr_vision = await asyncio.gather(
            _run_ocr(),
            _run_vision_embed(),
            return_exceptions=False,
        )
        step_results.extend([sr_ocr, sr_vision])

        # Extract OCR text (may be empty on failure)
        ocr_text = ""
        if sr_ocr.status == "ok":
            ocr_text = sr_ocr.outputs.get("content_text") or sr_ocr.outputs.get("text", "")

        vision_vector_ref = ""
        if sr_vision.status == "ok":
            vision_vector_ref = sr_vision.outputs.get("vector_ref", "")

        logger.info(
            "[ORCH]   trace=%s — OCR %s (%d chars), VisionEmbed %s (ref=%s)",
            trace_id[:12],
            sr_ocr.status, len(ocr_text),
            sr_vision.status, vision_vector_ref[:20] if vision_vector_ref else "—",
        )

        # ── Sequential: TextEmbed (only if OCR produced text) ──
        text_vector_ref = ""
        if ocr_text.strip():
            sr_text_embed = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="text_embed",
                intent="ingest.embed",
                inputs={"text": ocr_text},
                timeout_ms=10000,
                prev_exec_node_id=sr_ocr.exec_node_id,  # depends on OCR
            )
            step_results.append(sr_text_embed)
            if sr_text_embed.status == "ok":
                text_vector_ref = sr_text_embed.outputs.get("vector_ref", "")
        else:
            logger.info(
                "[ORCH]   trace=%s — skipping text_embed (no OCR text)",
                trace_id[:12],
            )

        # ── Sequential: GraphBuilder (only if OCR produced text) ──
        if ocr_text.strip():
            prev_node = step_results[-1].exec_node_id  # text_embed or ocr
            sr_graph = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="graph_builder",
                intent="ingest.graph",
                inputs={"content_text": ocr_text, "memory_id": ""},
                timeout_ms=10000,
                prev_exec_node_id=prev_node,
            )
            step_results.append(sr_graph)
        else:
            logger.info(
                "[ORCH]   trace=%s — skipping graph_builder (no OCR text)",
                trace_id[:12],
            )

        # ── Commit memory card (always, even on partial failure) ──
        memory_id = _new_id()
        summary = (ocr_text or f"Image: {fname}")[:500]
        card_type = "file_capture"

        # Determine overall status
        any_ok = sr_ocr.status == "ok" or sr_vision.status == "ok"
        overall_status = "ok" if any_ok else "error"

        metadata = {
            "blob_id": blob_id,
            "source_id": source_id,
            "file_path": path,
            "mime": mime,
            "size_bytes": size_bytes,
            "trace_id": trace_id,
            "pipeline": "ocr",
            "ocr_text": ocr_text[:1000] if ocr_text else None,
            "ocr_status": sr_ocr.status,
            "vision_vector_ref": vision_vector_ref or None,
            "vision_status": sr_vision.status,
            "text_vector_ref": text_vector_ref or None,
        }
        db_repo.insert_memory_card(
            memory_id=memory_id,
            card_type=card_type,
            summary=summary,
            metadata=metadata,
        )
        logger.info(
            "[ORCH]   trace=%s — memory_card=%s created (ocr=%s, vision=%s)",
            trace_id[:12], memory_id[:12], sr_ocr.status, sr_vision.status,
        )

        # Best-effort graph upsert
        try:
            self._upsert_graph(memory_id, summary, step_results)
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
    async def chat(self, user_text: str, *, trace_id: str | None = None) -> ChatResult:
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

        # ── Step 1: Retrieval ─────────────────────────────
        sr_retrieval = await self._dispatch_tool(
            trace_id=trace_id,
            tool_name="retrieval",
            intent="chat.retrieve",
            inputs={"query": user_text, "limit": 10},
            timeout_ms=10000,
            prev_exec_node_id=prev_exec_node_id,
        )
        step_results.append(sr_retrieval)
        prev_exec_node_id = sr_retrieval.exec_node_id
        context = sr_retrieval.outputs.get("results", [])

        # ── Step 2: Weave ─────────────────────────────────
        use_llm = await llm_available()
        if use_llm:
            logger.info("[ORCH]   trace=%s — using LLM for weave", trace_id[:12])
            llm_result = await weave_with_llm(user_text, context)
            # Still dispatch through registry for tracing
            sr_weave = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="weaver",
                intent="chat.weave",
                inputs={"query": user_text, "context": context, "_llm_override": llm_result},
                timeout_ms=30000,
                prev_exec_node_id=prev_exec_node_id,
            )
        else:
            sr_weave = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="weaver",
                intent="chat.weave",
                inputs={"query": user_text, "context": context},
                timeout_ms=30000,
                prev_exec_node_id=prev_exec_node_id,
            )
        step_results.append(sr_weave)
        prev_exec_node_id = sr_weave.exec_node_id
        answer = sr_weave.outputs.get("answer", "")
        citations = sr_weave.outputs.get("citations", [])

        # ── Step 3: Verify ────────────────────────────────
        if use_llm:
            verify_result = await verify_with_llm(answer, context)
            sr_verify = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="verifier",
                intent="chat.verify",
                inputs={"answer": answer, "context": context, "_llm_override": verify_result},
                timeout_ms=15000,
                prev_exec_node_id=prev_exec_node_id,
            )
        else:
            sr_verify = await self._dispatch_tool(
                trace_id=trace_id,
                tool_name="verifier",
                intent="chat.verify",
                inputs={"answer": answer, "context": context},
                timeout_ms=15000,
                prev_exec_node_id=prev_exec_node_id,
            )
        step_results.append(sr_verify)
        verdict = sr_verify.outputs.get("verdict", "")

        # If no LLM and no citations, mark needs_review
        if not use_llm and not citations:
            verdict = "needs_review"

        # ── Persist conversation turn ─────────────────────
        turn_id = _new_id()
        db_repo.insert_conversation_turn(turn_id, user_text, answer, trace_id=trace_id)

        db_repo.finish_exec_trace(trace_id, "done")

        return ChatResult(
            trace_id=trace_id,
            answer=answer,
            citations=citations,
            verdict=verdict,
            steps=step_results,
            status="ok",
        )

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

    def _upsert_graph(self, memory_id: str, summary: str, step_results: list[StepResult]) -> None:
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
                        # Fix memory_id in edges if it was placeholder
                        if e.get("from_node_id", "").startswith("mem:"):
                            e["from_node_id"] = f"mem:{memory_id}"
                        prov = e.get("provenance", {})
                        if not prov.get("tool_call_id"):
                            prov["tool_call_id"] = sr.call_id
                        graph_edges.append(GraphEdgeIn(**{**e, "provenance": prov}))

            graph.upsert_nodes([mem_node] + entity_nodes)
            if graph_edges:
                graph.upsert_edges(graph_edges)

        except Exception:
            logger.debug("Graph service not available or failed", exc_info=True)
