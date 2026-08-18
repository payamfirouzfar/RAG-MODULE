"""Citation tests: every citation maps to retrieved evidence, no
fabricated sources."""

from __future__ import annotations

from src.generator import OfflineGenerator
from src.retriever import RetrievalResult


def _result(chunk_id: str, doc_id: str, url: str) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id, document_id=doc_id, text="evidence text", url=url, title="T", score=0.9
    )


def test_every_source_maps_to_a_retrieved_result():
    results = [
        _result("c1", "d1", "http://x/1"),
        _result("c2", "d2", "http://x/2"),
        _result("c3", "d3", "http://x/3"),
    ]
    generator = OfflineGenerator()
    output = generator(("question", results))

    retrieved_chunk_ids = {r.chunk_id for r in results}
    cited_chunk_ids = {s["chunk_id"] for s in output["sources"]}
    assert cited_chunk_ids.issubset(retrieved_chunk_ids)


def test_no_sources_fabricated_when_nothing_retrieved():
    generator = OfflineGenerator()
    output = generator(("question", []))
    assert output["sources"] == []


def test_source_count_never_exceeds_retrieved_count():
    results = [_result("c1", "d1", "http://x/1")]
    generator = OfflineGenerator()
    output = generator(("question", results))
    assert len(output["sources"]) <= len(results)


def test_source_urls_are_real_retrieved_urls():
    results = [_result("c1", "d1", "http://real-source.example.com")]
    generator = OfflineGenerator()
    output = generator(("question", results))
    assert output["sources"][0]["url"] == "http://real-source.example.com"
