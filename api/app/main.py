from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.migrate import run_migration
from app.routers import cards, chat, graph, health, ingest, tools
from app.routers import capture as capture_router
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run idempotent schema migration
    run_migration()

    # Launch continuous background tasks
    watcher_task = asyncio.create_task(watch_loop(), name="file-watcher")
    worker_task = asyncio.create_task(worker_loop(), name="job-worker")

    yield

    # Shutdown: cancel background tasks
    watcher_task.cancel()
    worker_task.cancel()
    for t in (watcher_task, worker_task):
        try:
            await t
        except asyncio.CancelledError:
            pass


app = FastAPI(title="EchoGarden", docs_url="/docs", lifespan=lifespan)

app.include_router(health.router)
app.include_router(cards.router)
app.include_router(tools.router)
app.include_router(ingest.router)
app.include_router(chat.router)
app.include_router(graph.router)
app.include_router(capture_router.router)
