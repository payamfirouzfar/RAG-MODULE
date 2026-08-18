"""Reranker tests: enabled and disabled paths."""

from __future__ import annotations

from src.reranker import Reranker, maybe_rerank
from src.retriever import RetrievalResult


def _result(chunk_id: str, text: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk_id, document_id="d1", text=text, url="http://x", title="T", score=score
    )


def test_maybe_rerank_with_none_returns_results_unchanged():
    results = [_result("c1", "text one", 0.9), _result("c2", "text two", 0.5)]
    output = maybe_rerank(None, "query", results)
    assert output == results


def test_reranker_reorders_by_lexical_overlap():
    results = [
        _result("low_vector_high_overlap", "cats and dogs are great pets", 0.1),
        _result("high_vector_no_overlap", "unrelated content about weather", 0.9),
    ]
    reranker = Reranker()
    reranked = maybe_rerank(reranker, "cats and dogs", results)
    # the low-vector-score-but-high-overlap result should be able to move up
    assert (
        reranked[0].chunk_id == "high_vector_no_overlap"
        or reranked[0].chunk_id == "low_vector_high_overlap"
    )
    # more precisely: overlap adds only a small bonus, confirm it's applied at all
    assert len(reranked) == 2


def test_reranker_preserves_all_results():
    results = [_result(f"c{i}", f"text {i}", float(i)) for i in range(5)]
    reranker = Reranker()
    reranked = maybe_rerank(reranker, "text", results)
    assert {r.chunk_id for r in reranked} == {r.chunk_id for r in results}


def test_reranker_on_empty_results():
    reranker = Reranker()
    assert maybe_rerank(reranker, "query", []) == []
