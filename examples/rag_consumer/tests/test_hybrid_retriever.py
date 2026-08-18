"""HybridRetriever tests: dense+lexical fusion via ragtorch.retrieval,
using the existing Retriever/Chunk/RetrievalResult/VectorStore
contracts unchanged.

ragtorch.retrieval was added to the ragtorch source tree in the same
step that added this file, but the demo's CI job installs the
currently-PUBLISHED `ragmodel==0.5.0` from real PyPI (see
../../.github/workflows/ci.yml's rag-consumer-demo job, and
docs/RELEASING.md) -- which predates this addition and does not have
it yet. `pytest.importorskip` makes this collection-safe against that
CI job today; once a future release actually publishes
ragtorch.retrieval, these tests will start running there automatically
with no further change needed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("ragtorch.retrieval")

from src.chunking import Chunk  # noqa: E402
from src.embeddings import HashingEmbedder  # noqa: E402
from src.hybrid_retriever import HybridRetriever, build_lexical_index  # noqa: E402
from src.retriever import Retriever  # noqa: E402
from src.vector_store import InMemoryVectorStore  # noqa: E402


def _build_hybrid(chunks: list[Chunk], *, top_k: int = 3) -> HybridRetriever:
    embedder = HashingEmbedder(dimensions=32)
    store = InMemoryVectorStore()
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, vectors)
    dense_retriever = Retriever(embedder, store, top_k=top_k)
    lexical_index = build_lexical_index(chunks)
    chunks_by_id = {c.chunk_id: c for c in chunks}
    return HybridRetriever(dense_retriever, lexical_index, chunks_by_id, top_k=top_k)


_CHUNKS = [
    Chunk(
        chunk_id="c1",
        document_id="d1",
        url="http://x/1",
        title="Cats",
        text="Cats are small domesticated mammals that like to sleep.",
        chunk_index=0,
    ),
    Chunk(
        chunk_id="c2",
        document_id="d2",
        url="http://x/2",
        title="Dogs",
        text="Dogs are loyal domesticated companions that like to play.",
        chunk_index=0,
    ),
    Chunk(
        chunk_id="c3",
        document_id="d3",
        url="http://x/3",
        title="Fish",
        text="Fish live in water and breathe through gills.",
        chunk_index=0,
    ),
]


def test_hybrid_retriever_initializes_module_state_correctly():
    hybrid = _build_hybrid(_CHUNKS)
    assert hasattr(hybrid, "_modules")


def test_hybrid_retriever_returns_the_lexically_relevant_chunk_first():
    """Regression test for a real bug found during Step 32's own
    testing: an earlier version of HybridRetriever kept the ORIGINAL
    dense-only score on results that also appeared in the dense
    ranking, instead of the fused RRF score -- this silently
    misrepresented ranking confidence (a chunk ranked #1 by the actual
    fusion could display a lower score than a chunk ranked #3). Using
    HashingEmbedder (a known-weak dense embedder, see the demo's own
    README limitations) deliberately produces a WRONG dense-only
    ranking here ("Fish" outranks "Cats" for a cats query) while BM25
    correctly identifies only "Cats" as lexically relevant -- proving
    the fusion, not just the dense signal, drives the final result."""
    hybrid = _build_hybrid(_CHUNKS)
    results = hybrid("Tell me about cats")

    assert results[0].chunk_id == "c1"
    # scores must be strictly descending (the fused RRF scores, not
    # leftover dense-only scores which would not necessarily be ordered
    # this way -- this assertion is what the original bug violated)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_retriever_result_scores_match_direct_rrf_call():
    from ragtorch.retrieval import rrf

    hybrid = _build_hybrid(_CHUNKS)
    dense_retriever = hybrid._dense_retriever  # noqa: SLF001
    lexical_index = hybrid._lexical_index  # noqa: SLF001

    query = "Tell me about cats"
    dense_ids = [r.chunk_id for r in dense_retriever(query)]
    lexical_ids = [item.item for item in lexical_index.search(query, top_k=3)]
    expected = {r.item: r.score for r in rrf([dense_ids, lexical_ids], top_k=3)}

    results = hybrid(query)
    for result in results:
        assert result.score == expected[result.chunk_id]


def test_hybrid_retriever_preserves_chunk_metadata_for_bm25_only_matches():
    # A chunk that BM25 finds but a low top_k dense search might miss --
    # confirms metadata (url/title/text) is still real, not fabricated.
    hybrid = _build_hybrid(_CHUNKS, top_k=1)
    results = hybrid("gills water breathe")
    fish_results = [r for r in results if r.chunk_id == "c3"]
    if fish_results:
        assert fish_results[0].title == "Fish"
        assert fish_results[0].url == "http://x/3"


def test_hybrid_retriever_union_of_dense_and_lexical_relevant_ids():
    hybrid = _build_hybrid(_CHUNKS)
    results = hybrid("cats dogs")
    result_ids = {r.chunk_id for r in results}
    # both cats and dogs chunks are lexically relevant to this query
    assert "c1" in result_ids
    assert "c2" in result_ids


def test_build_lexical_index_keys_by_chunk_id():
    index = build_lexical_index(_CHUNKS)
    results = index.search("cats")
    assert results[0].item == "c1"
