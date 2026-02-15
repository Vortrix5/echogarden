import pytest

from app.orchestrator.models import PipelineType
from app.orchestrator.router import build_ingest_steps, choose_pipeline, is_image_pipeline


@pytest.mark.parametrize(
    ("mime", "path", "pipeline"),
    [
        ("image/png", "/w/shot.png", PipelineType.ocr),
        ("application/octet-stream", "/w/photo.JPG", PipelineType.ocr),
        ("audio/mpeg", "/w/memo.mp3", PipelineType.asr),
        ("application/octet-stream", "/w/memo.m4a", PipelineType.asr),
        ("application/pdf", "/w/paper.pdf", PipelineType.doc_parse),
        ("text/plain", "/w/notes.txt", PipelineType.doc_parse),
        ("application/octet-stream", "/w/unknown.bin", PipelineType.doc_parse),
    ],
)
def test_choose_pipeline(mime, path, pipeline):
    assert choose_pipeline(mime, path) == pipeline


def test_mime_wins_over_extension():
    assert choose_pipeline("image/png", "/w/misnamed.pdf") == PipelineType.ocr


def test_only_images_use_the_parallel_branch():
    assert is_image_pipeline(PipelineType.ocr)
    assert not is_image_pipeline(PipelineType.doc_parse)


@pytest.mark.parametrize(
    ("pipeline", "first"),
    [(PipelineType.doc_parse, "doc_parse"), (PipelineType.asr, "asr")],
)
def test_sequential_pipelines_enrich_then_embed_then_graph(pipeline, first):
    steps = build_ingest_steps(pipeline, path="/w/f", blob_id="b", source_id="s", mime="m")

    assert [s.tool_name for s in steps] == [first, "summarizer", "extractor", "text_embed", "graph_builder"]


def test_image_steps_are_not_built_by_the_router():
    with pytest.raises(ValueError):
        build_ingest_steps(PipelineType.ocr, path="/w/a.png", blob_id="b", source_id="s", mime="image/png")
