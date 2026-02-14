from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.migrate import run_migration
from app.routers import cards, chat, health, ingest, tools

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run idempotent schema migration
    run_migration()
    yield


app = FastAPI(title="EchoGarden", docs_url="/docs", lifespan=lifespan)

app.include_router(health.router)
app.include_router(cards.router)
app.include_router(tools.router)
app.include_router(ingest.router)
app.include_router(chat.router)
