import os

# Set before any app module is imported: config is read at import time, and
# tests must never reach a real Ollama, Qdrant or Tika.
os.environ["EG_OLLAMA_URL"] = ""
os.environ["QDRANT_URL"] = "http://127.0.0.1:9"
os.environ["TIKA_URL"] = "http://127.0.0.1:9"
os.environ["EG_WHISPER_MODE"] = "stub"
os.environ["EG_OPENCLIP_MODE"] = "stub"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = str(tmp_path / "sqlite" / "echogarden.db")
    monkeypatch.setattr("app.db.conn.EG_DB_PATH", path)
    monkeypatch.setattr("app.db.migrate.EG_DB_PATH", path)
    from app.db.migrate import run_migration

    run_migration()
    return path


@pytest.fixture
def fake_embed(monkeypatch):
    calls = []

    async def embed_text(text, memory_id="", source_type="file", created_at=""):
        calls.append(memory_id)
        return {"vector_ref": f"qdrant:text:{memory_id}"}

    monkeypatch.setattr("app.tools.text_embed_impl.embed_text", embed_text)
    return calls


@pytest.fixture
def client(db):
    # No context manager: the lifespan (watcher, worker, model preload) stays off.
    from app.main import app

    return TestClient(app)
