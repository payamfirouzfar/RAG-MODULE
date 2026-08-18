"""Optional reranker(Module). The pipeline works with reranker=None."""

from __future__ import annotations

from ragtorch import Module

from .retriever import RetrievalResult


class Reranker(Module):
    """Deterministic lexical-overlap reranker: no ML model, no extra
    dependency. Rescoring purely by query/chunk word overlap on top of
    the retriever's own vector score, so reranking demonstrably changes
    ordering without requiring a cross-encoder model download."""

    def forward(
        self, payload: tuple[str, list[RetrievalResult]], *, context=None
    ) -> list[RetrievalResult]:
        query, results = payload
        query_words = set(query.lower().split())

        def overlap_score(result: RetrievalResult) -> float:
            text_words = set(result.text.lower().split())
            overlap = len(query_words & text_words)
            return result.score + 0.01 * overlap

        return sorted(results, key=overlap_score, reverse=True)


def maybe_rerank(
    reranker: Reranker | None, query: str, results: list[RetrievalResult]
) -> list[RetrievalResult]:
    """The pipeline must still work with reranker=None -- this helper is
    what pipeline.py calls, so "no reranker" is a first-class, tested
    path, not a special case bolted on."""
    if reranker is None:
        return results
    return reranker((query, results))
