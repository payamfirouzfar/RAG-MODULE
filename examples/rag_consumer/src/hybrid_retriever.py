"""HybridRetriever: dense (existing Retriever) + lexical (BM25) fused
with RRF, using ragtorch.retrieval directly.

Application-level, NOT part of ragtorch -- exactly the pattern
Retriever/Reranker/Generator already use (a Module subclass wrapping
application logic on top of ragtorch primitives). ragtorch.retrieval's
BM25Index/rrf are plain Python (not Modules, see their own docstrings);
this class is what gives them an execution identity within the
existing Sequential pipeline, following the demo's own established
RetrieveStage pattern rather than introducing a new composition style.

Uses the existing Retriever/Chunk/RetrievalResult/VectorStore contracts
unchanged -- no redesign of any of them.
"""

from __future__ import annotations

from ragtorch import Module
from ragtorch.retrieval import BM25Index, rrf

from .chunking import Chunk
from .retriever import RetrievalResult, Retriever


def build_lexical_index(chunks: list[Chunk]) -> BM25Index[str]:
    """Builds a BM25Index over the same chunks already indexed into the
    dense VectorStore, keyed by the same chunk_id used everywhere else
    in this demo (RetrievalResult.chunk_id, Chunk.chunk_id) -- so fused
    ids map back to chunk metadata using the exact same lookup the
    dense-only path already relies on."""
    return BM25Index({chunk.chunk_id: chunk.text for chunk in chunks})


class HybridRetriever(Module):
    """Fuses the existing dense Retriever's ranking with a BM25 lexical
    ranking via Reciprocal Rank Fusion, then maps the fused chunk_ids
    back to full RetrievalResult objects using the dense retriever's
    own results (falling back to the lexical index's chunk text if a
    chunk was found only by BM25 and never appeared in the dense
    results) -- so citations/sources continue to carry real chunk
    metadata exactly as the dense-only path already does."""

    def __init__(
        self,
        dense_retriever: Retriever,
        lexical_index: BM25Index[str],
        chunks_by_id: dict[str, Chunk],
        *,
        top_k: int,
    ) -> None:
        super().__init__()
        self._dense_retriever = dense_retriever
        self._lexical_index = lexical_index
        self._chunks_by_id = chunks_by_id
        self._top_k = top_k

    def forward(self, query: str, *, context=None) -> list[RetrievalResult]:
        dense_results = self._dense_retriever(query, context=context)
        lexical_results = self._lexical_index.search(query, top_k=self._top_k)

        dense_ids = [r.chunk_id for r in dense_results]
        lexical_ids = [item.item for item in lexical_results]

        fused = rrf([dense_ids, lexical_ids], top_k=self._top_k)

        dense_by_id = {r.chunk_id: r for r in dense_results}
        results: list[RetrievalResult] = []
        for ranked in fused:
            chunk_id = ranked.item
            # `.score` is always the fused RRF score, never the
            # original dense-only or lexical-only score -- a real bug
            # was found and fixed here during this step's own testing:
            # an earlier version kept the dense RetrievalResult's
            # original score unchanged, which silently misrepresented
            # the fused ranking's own confidence (e.g. a chunk ranked
            # first by RRF could display a lower score than a chunk
            # ranked third, because it was still showing dense-only
            # numbers) -- caught by comparing this method's output
            # against a direct rrf() call on the same inputs.
            if chunk_id in dense_by_id:
                dense_result = dense_by_id[chunk_id]
                results.append(
                    RetrievalResult(
                        chunk_id=dense_result.chunk_id,
                        document_id=dense_result.document_id,
                        text=dense_result.text,
                        url=dense_result.url,
                        title=dense_result.title,
                        score=ranked.score,
                    )
                )
                continue
            # A chunk BM25 found but dense retrieval did not return --
            # look up its metadata from the known chunk set so sources
            # remain real, never fabricated.
            chunk = self._chunks_by_id.get(chunk_id)
            if chunk is not None:
                results.append(
                    RetrievalResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        text=chunk.text,
                        url=chunk.url,
                        title=chunk.title,
                        score=ranked.score,
                    )
                )
        return results
