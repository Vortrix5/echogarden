def test_healthz_reports_each_dependency(client):
    body = client.get("/healthz").json()

    assert body["sqlite"] == "ok"
    assert body["qdrant"] == "unreachable"
    assert body["llm"] == "unavailable"
    assert body["ok"] is False
