from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.migrate import run_migration
from app.routers import cards, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: run idempotent schema migration
    run_migration()
    yield


app = FastAPI(title="EchoGarden", docs_url="/docs", lifespan=lifespan)

app.include_router(health.router)
app.include_router(cards.router)
