import random

from app.db import repo


def _add(memory_id, summary):
    repo.insert_memory_card(memory_id=memory_id, card_type="note", summary=summary)


def test_stronger_keyword_match_scores_higher(db):
    rng = random.Random(0)
    filler = ["alpha", "beta", "gamma", "delta", "omega", "sigma", "kappa", "theta"]
    for i in range(50):
        _add(f"filler{i}", " ".join(rng.choices(filler, k=12)))
    _add("strong", "qdrant qdrant qdrant vector search engine")
    _add("weak", "a long note " + " ".join(rng.choices(filler, k=40)) + " mentions qdrant once")

    scores = dict(repo.search_fts_phase5("qdrant"))

    assert set(scores) == {"strong", "weak"}
    assert scores["strong"] > scores["weak"]
    assert all(0.0 < s < 1.0 for s in scores.values())


def test_query_with_only_fts_syntax_returns_nothing(db):
    _add("a", "anything")

    assert repo.search_fts_phase5('"*:^()') == []
