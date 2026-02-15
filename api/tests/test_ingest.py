from app.db.conn import get_conn

TEXT = "EchoGarden is a local-first knowledge garden. It remembers what you read."


def _card(memory_id):
    conn = get_conn()
    try:
        return conn.execute("SELECT * FROM memory_card WHERE memory_id = ?", (memory_id,)).fetchone()
    finally:
        conn.close()


def test_inline_ingest_creates_a_card(client, fake_embed):
    body = client.post("/ingest", json={"text": TEXT}).json()

    assert body["status"] == "ok"
    card = _card(body["memory_id"])
    assert card["content_text"] == TEXT
    assert fake_embed == [body["memory_id"]]


async def test_ingesting_the_same_blob_twice_creates_one_card(db, fake_embed):
    from app.orchestrator.orchestrator import Orchestrator

    orch = Orchestrator()
    args = dict(blob_id="blob-1", source_id="src-1", path="<inline>", mime="text/plain", text=TEXT)

    first = await orch.ingest_blob(**args)
    second = await orch.ingest_blob(**args)

    assert first.status == "ok"
    assert second.status == "idempotent_skip"
    assert second.memory_id == first.memory_id
    conn = get_conn()
    try:
        assert conn.execute("SELECT COUNT(*) FROM memory_card").fetchone()[0] == 1
    finally:
        conn.close()
    assert len(fake_embed) == 1
