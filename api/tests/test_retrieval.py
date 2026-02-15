import math
from datetime import datetime, timedelta, timezone

import pytest

from app.retrieval import service
from app.retrieval.graph_expand import GraphCandidate
from app.retrieval.models import RetrieveRequest


def _ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture
def signals(monkeypatch):
    """Replace every retrieval backend with fixed signals for three cards."""
    cards = {
        "both": {"memory_id": "both", "summary": "a", "type": "note", "created_at": _ago(0)},
        "graph": {"memory_id": "graph", "summary": "b", "type": "browser_highlight", "created_at": _ago(60)},
        "noise": {"memory_id": "noise", "summary": "c", "type": "browser_visit", "created_at": _ago(0)},
    }
    monkeypatch.setattr(service, "_fts_search", lambda *a: [("both", 0.8), ("noise", 0.1)])

    async def semantic(query, limit):
        return [("both", 0.6)]

    monkeypatch.setattr(service, "_semantic_search", semantic)
    monkeypatch.setattr(
        service,
        "expand_from_seeds",
        lambda seeds, hops: [GraphCandidate(memory_id="graph", graph_score=0.6, via_entity_ids=["ent:x"])],
    )
    monkeypatch.setattr(service, "_fetch_cards", lambda ids: {i: cards[i] for i in ids if i in cards})


async def test_signals_are_combined_with_the_documented_weights(signals):
    results = (await service.hybrid_retrieve(RetrieveRequest(query="q"))).results
    by_id = {r.memory_id: r for r in results}

    expected_both = service.W_SEMANTIC * 0.6 + service.W_FTS * 0.8 + service.W_RECENCY * 1.0
    assert by_id["both"].final_score == pytest.approx(expected_both, abs=1e-3)

    expected_graph = service.W_GRAPH * 0.6 + service.W_RECENCY * math.exp(-2) + 0.10
    assert by_id["graph"].final_score == pytest.approx(expected_graph, abs=1e-3)
    assert by_id["graph"].signals.source_boost == 0.10
    assert by_id["graph"].graph_path.via_entity_ids == ["ent:x"]


async def test_results_are_ranked_and_weak_matches_dropped(signals):
    results = (await service.hybrid_retrieve(RetrieveRequest(query="q"))).results

    # "noise" scores below zero after its source penalty, is clamped to 0 and filtered out.
    assert [r.memory_id for r in results] == ["both", "graph"]
    assert results[0].reasons == ["fts_match", "semantic_text"]
    assert results[1].reasons == ["graph_expand"]


async def test_source_type_filter(signals):
    req = RetrieveRequest(query="q", source_types=["browser_highlight"])
    results = (await service.hybrid_retrieve(req)).results

    assert [r.memory_id for r in results] == ["graph"]


def test_weights_sum_to_one():
    assert service.W_SEMANTIC + service.W_FTS + service.W_GRAPH + service.W_RECENCY == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("created_at", "expected"),
    [
        (_ago(0), 1.0),
        (_ago(30), math.exp(-1)),
        (_ago(90), math.exp(-3)),
        ((datetime.now(timezone.utc) + timedelta(days=5)).isoformat(), 1.0),
        (None, 0.0),
        ("not a date", 0.0),
    ],
)
def test_recency_decays_exponentially(created_at, expected):
    assert service._recency_score(created_at) == pytest.approx(expected, abs=1e-3)


def test_recency_treats_naive_timestamps_as_utc():
    naive = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None).isoformat(sep=" ")

    assert service._recency_score(naive) == pytest.approx(math.exp(-1), abs=1e-3)
