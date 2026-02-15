from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.migrate import run_migration
from app.routers import cards, chat, graph, health, ingest, tools
from app.routers import capture as capture_router
from app.routers import capture_browser
from app.routers import exec_trace, tool_calls
from app.routers import debug as debug_router
from app.capture.watcher import watch_loop
from app.workers.job_worker import worker_loop

import asyncio
import logging

# Import agents so they self-register with the tool registry on startup.
import app.agents.doc_parse  # noqa: F401
import app.agents.ocr  # noqa: F401
import app.agents.asr  # noqa: F401
import app.agents.vision_embed  # noqa: F401
import app.agents.text_embed  # noqa: F401
import app.agents.retrieval  # noqa: F401
import app.agents.graph_builder  # noqa: F401
import app.agents.weaver  # noqa: F401
import app.agents.verifier  # noqa: F401
import app.agents.summarizer  # noqa: F401  (Phase 6)
import app.agents.extractor  # noqa: F401  (Phase 6)
import app.agents.image_caption  # noqa: F401  (Phase 7: caption fallback)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run idempotent schema migration
    run_migration()

    # Pre-load ML models in background so first ingest doesn't timeout
    preload_task = asyncio.create_task(_preload_models(), name="model-preload")

    # Launch continuous background tasks
    watcher_task = asyncio.create_task(watch_loop(), name="file-watcher")
    worker_task = asyncio.create_task(worker_loop(), name="job-worker")

    yield

    # Shutdown: cancel background tasks
    preload_task.cancel()
    watcher_task.cancel()
    worker_task.cancel()
    for t in (preload_task, watcher_task, worker_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


async def _preload_models():
    """Warm up ML models in background threads so first tool calls are fast."""
    logger = logging.getLogger("echogarden.preload")
    import os
    openclip_mode = os.environ.get("EG_OPENCLIP_MODE", "local")

    # Preload sentence-transformers
    try:
        logger.info("Pre-loading sentence-transformers model...")
        from app.tools.text_embed_impl import _load_model as load_st
        await asyncio.to_thread(load_st)
        logger.info("Sentence-transformers model ready.")
    except Exception:
        logger.exception("Failed to preload sentence-transformers")

    # Preload OpenCLIP (if not stub)
    if openclip_mode != "stub":
        try:
            logger.info("Pre-loading OpenCLIP model...")
            from app.tools.vision_embed_impl import _load_model as load_clip
            await asyncio.to_thread(load_clip)
            logger.info("OpenCLIP model ready.")

            # Ensure Qdrant vision collection exists
            from app.tools.vision_embed_impl import _VECTOR_DIM
            from app.tools.qdrant_client import ensure_collection as _ensure_col
            _ensure_col("vision", _VECTOR_DIM)
            logger.info("Qdrant 'vision' collection ready (dim=%d).", _VECTOR_DIM)
        except Exception:
            logger.exception("Failed to preload OpenCLIP")


app = FastAPI(title="EchoGarden", docs_url="/docs", lifespan=lifespan)

app.include_router(health.router)
app.include_router(cards.router)
app.include_router(tools.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(graph.router)
app.include_router(capture_router.router)
app.include_router(capture_browser.router)
app.include_router(exec_trace.router)
app.include_router(tool_calls.router)
app.include_router(debug_router.router)
