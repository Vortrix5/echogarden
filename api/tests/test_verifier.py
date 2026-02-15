import pytest

from app.agents.verifier import VerifierAgent, _heuristic_verify
from app.core.tool_contracts import ToolEnvelope
from app.llm.ollama_client import LLMUnavailableError
from app.orchestrator import llm as orch_llm

EVIDENCE = [{"memory_id": "a" * 32, "summary": "Qdrant stores the vectors."}]
CITATIONS = [{"memory_id": "a" * 32, "quote": "Qdrant stores the vectors."}]


def _llm_returns(monkeypatch, raw=None, error=None):
    async def fake(prompt, **kwargs):
        if error:
            raise error
        return raw

    monkeypatch.setattr("app.llm.ollama_client.ollama_generate_json", fake)
    monkeypatch.setattr(orch_llm, "ollama_generate_json", fake)


async def _verify(**inputs):
    env = ToolEnvelope(callee="verifier", inputs={"question": "q", "answer": "x", **inputs})
    return await VerifierAgent().execute(env)


async def test_reads_verdict_from_fenced_json(monkeypatch):
    _llm_returns(monkeypatch, '```json\n{"verdict": "revise", "revised_answer": "y", "issues": ["z"]}\n```')

    out = await _verify(evidence=EVIDENCE, citations=CITATIONS)

    assert out == {"verdict": "revise", "revised_answer": "y", "issues": ["z"]}


async def test_reads_json_embedded_in_prose(monkeypatch):
    _llm_returns(monkeypatch, 'Sure, here you go: {"verdict": "abstain"} hope that helps')

    assert (await _verify(evidence=EVIDENCE))["verdict"] == "abstain"


async def test_unknown_verdict_fails_open_to_pass(monkeypatch):
    # Current behaviour, listed under known limitations in the README.
    _llm_returns(monkeypatch, '{"verdict": "maybe"}')

    assert (await _verify(evidence=EVIDENCE))["verdict"] == "pass"


async def test_unparseable_output_falls_back_to_heuristic(monkeypatch):
    _llm_returns(monkeypatch, "not json at all")

    assert (await _verify(evidence=[], citations=[]))["verdict"] == "abstain"


async def test_unavailable_llm_falls_back_to_heuristic(monkeypatch):
    _llm_returns(monkeypatch, error=LLMUnavailableError("down"))

    assert (await _verify(evidence=EVIDENCE, citations=[]))["verdict"] == "revise"


async def test_precomputed_result_is_returned_unchanged():
    out = await _verify(_llm_override={"verdict": "abstain", "issues": ["none"]})

    assert out == {"verdict": "abstain", "revised_answer": "", "issues": ["none"]}


@pytest.mark.parametrize(
    ("answer", "citations", "evidence", "verdict"),
    [
        ("anything", CITATIONS, [], "abstain"),
        ("no refs here", [], EVIDENCE, "revise"),
        (f"Qdrant [{'a' * 32}] stores vectors", [], EVIDENCE, "pass"),
        ("anything", CITATIONS, EVIDENCE, "pass"),
    ],
)
def test_heuristic_verdicts(answer, citations, evidence, verdict):
    assert _heuristic_verify(answer, citations, evidence)["verdict"] == verdict


async def test_orchestrator_verify_falls_back_when_llm_is_down(monkeypatch):
    _llm_returns(monkeypatch, error=LLMUnavailableError("down"))

    out = await orch_llm.verify_with_llm("q", "no refs", EVIDENCE)

    assert out["verdict"] == "revise"
    assert out["llm_used"] is False
