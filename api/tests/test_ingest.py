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
