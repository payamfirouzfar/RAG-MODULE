"""Retriever(Module): the first real ragtorch integration point.

Verified against the installed ragmodel==0.5.0 package via
inspect.signature before writing this: Module.__init__(self) -> None
takes no arguments, and Module.__setattr__ registers Module-typed
attributes as children only if self._modules already exists -- which
requires super().__init__() to run FIRST. This class calls
super().__init__() as the very first line of __init__, exactly to
avoid that failure mode.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ragtorch import Module

from .embeddings import Embedder
from .vector_store import ScoredChunk, VectorStore


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: str
    document_id: str
    text: str
    url: str
    title: str
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def _to_retrieval_result(scored: ScoredChunk) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=scored.chunk.chunk_id,
        document_id=scored.chunk.document_id,
        text=scored.chunk.text,
        url=scored.chunk.url,
        title=scored.chunk.title,
        score=scored.score,
    )


class Retriever(Module):
    """Embeds a query, searches the vector store, and returns
    RetrievalResult objects with metadata preserved (chunk_id,
    document_id, url, title, score) -- everything a citation later
    needs.

    min_score (optional): results scoring below this threshold are
    dropped. This is what lets the pipeline correctly signal
    "insufficient evidence" for an out-of-domain question even when the
    vector store still returns its top_k nearest neighbors by
    construction -- a plain nearest-neighbor search never returns
    "nothing," it returns "the least-bad match," so filtering by score
    is the application's responsibility, not the vector store's or
    ragtorch's."""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        *,
        top_k: int,
        min_score: float | None = None,
    ) -> None:
        super().__init__()
        self._embedder = embedder
        self._vector_store = vector_store
        self._top_k = top_k
        self._min_score = min_score

    def forward(self, query: str, *, context=None) -> list[RetrievalResult]:
        query_vector = self._embedder.embed_query(query)
        scored_chunks = self._vector_store.search(query_vector, self._top_k)
        results = [_to_retrieval_result(sc) for sc in scored_chunks]
        if self._min_score is not None:
            results = [r for r in results if r.score >= self._min_score]
        return results
