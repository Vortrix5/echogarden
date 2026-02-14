"""Tool routing rules — choose pipeline based on mime/extension."""

from __future__ import annotations

import os

from app.orchestrator.models import PipelineType, ToolStep

# ── Mime / extension → pipeline mapping ───────────────────

_TEXT_MIMES = {"text/plain", "text/markdown", "text/csv", "text/x-log", "application/json"}
_DOC_MIMES = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
_IMAGE_MIMES_PREFIX = "image/"
_AUDIO_MIMES_PREFIX = "audio/"

_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".log"}
_DOC_EXTENSIONS = {".pdf", ".docx"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".svg"}
_AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".wma", ".opus"}


def choose_pipeline(mime: str, path: str) -> PipelineType:
    """Return the pipeline type for a given mime/path."""
    ext = os.path.splitext(path)[1].lower()

    # Image — handled via dedicated parallel branch in orchestrator
    if mime.startswith(_IMAGE_MIMES_PREFIX) or ext in _IMAGE_EXTENSIONS:
        return PipelineType.ocr

    # Audio
    if mime.startswith(_AUDIO_MIMES_PREFIX) or ext in _AUDIO_EXTENSIONS:
        return PipelineType.asr

    # Everything else -> doc_parse (text, pdf, docx, unknown)
    return PipelineType.doc_parse


def is_image_pipeline(pipeline: PipelineType) -> bool:
    """True when the orchestrator should use parallel OCR + VisionEmbed."""
    return pipeline == PipelineType.ocr


def build_ingest_steps(
    pipeline: PipelineType,
    *,
    path: str,
    blob_id: str,
    source_id: str,
    mime: str,
) -> list[ToolStep]:
    """Return an ordered list of ToolSteps for the chosen pipeline."""

    if pipeline == PipelineType.doc_parse:
        return [
            ToolStep(
                tool_name="doc_parse",
                intent="ingest.parse",
                inputs={"text": "", "path": path, "blob_id": blob_id},
                timeout_ms=15000,
            ),
            ToolStep(
                tool_name="text_embed",
                intent="ingest.embed",
                inputs={},  # filled at runtime from previous output
                timeout_ms=10000,
                depends_on=["doc_parse"],
            ),
            ToolStep(
                tool_name="graph_builder",
                intent="ingest.graph",
                inputs={},  # filled at runtime
                timeout_ms=10000,
                depends_on=["text_embed"],
            ),
        ]

    if pipeline == PipelineType.ocr:
        # Image pipeline is handled directly by the orchestrator
        # via _ingest_image() with parallel OCR + VisionEmbed branches.
        # This function should NOT be called for images.
        raise ValueError(
            "Image pipeline uses Orchestrator._ingest_image(), "
            "not build_ingest_steps()"
        )

    # asr
    return [
        ToolStep(
            tool_name="asr",
            intent="ingest.asr",
            inputs={"audio_path": path},
            timeout_ms=60000,
        ),
        ToolStep(
            tool_name="text_embed",
            intent="ingest.embed",
            inputs={},
            timeout_ms=10000,
            depends_on=["asr"],
        ),
        ToolStep(
            tool_name="graph_builder",
            intent="ingest.graph",
            inputs={},
            timeout_ms=10000,
            depends_on=["text_embed"],
        ),
    ]


def build_chat_steps() -> list[ToolStep]:
    """Return the ordered tool steps for a chat pipeline."""
    return [
        ToolStep(
            tool_name="retrieval",
            intent="chat.retrieve",
            inputs={},
            timeout_ms=10000,
        ),
        ToolStep(
            tool_name="weaver",
            intent="chat.weave",
            inputs={},
            timeout_ms=30000,
            depends_on=["retrieval"],
        ),
        ToolStep(
            tool_name="verifier",
            intent="chat.verify",
            inputs={},
            timeout_ms=15000,
            depends_on=["weaver"],
        ),
    ]
