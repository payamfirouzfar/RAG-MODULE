"""Retriever tests: top-k, score ordering, metadata preservation, empty
results. Also verifies correct ragtorch.Module initialization."""

from __future__ import annotations

from src.chunking import Chunk
from src.embeddings import HashingEmbedder
from src.retriever import Retriever
from src.vector_store import InMemoryVectorStore


def _chunk(chunk_id: str, text: str, doc_id: str = "d1") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        url=f"http://x/{doc_id}",
        title="Title",
        text=text,
        chunk_index=0,
    )


def test_retriever_initializes_module_state_correctly():
    """Regression guard for the exact mistake the task instruction
    warned about: a Module subclass that doesn't call super().__init__()
    silently fails to register child Modules. This confirms Retriever's
    internal ragtorch.Module state (._modules) exists after construction."""
    embedder = HashingEmbedder(dimensions=8)
    store = InMemoryVectorStore()
    retriever = Retriever(embedder, store, top_k=3)
    assert hasattr(retriever, "_modules"), "Module.__init__ was not called -- _modules is missing"


def test_retriever_returns_top_k_results():
    embedder = HashingEmbedder(dimensions=16)
    store = InMemoryVectorStore()
    chunks = [_chunk(f"c{i}", f"unique content number {i}") for i in range(5)]
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, vectors)

    retriever = Retriever(embedder, store, top_k=2)
    results = retriever("content number 2")
    assert len(results) == 2


def test_retriever_results_ordered_by_score_descending():
    embedder = HashingEmbedder(dimensions=16)
    store = InMemoryVectorStore()
    chunks = [
        _chunk("exact", "cats and dogs together"),
        _chunk("unrelated", "quantum physics equations"),
    ]
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, vectors)

    retriever = Retriever(embedder, store, top_k=2)
    results = retriever("cats and dogs together")
    assert results[0].score >= results[1].score


def test_retriever_preserves_metadata():
    embedder = HashingEmbedder(dimensions=8)
    store = InMemoryVectorStore()
    chunk = _chunk("c1", "some text", doc_id="doc-42")
    vectors = embedder.embed_documents([chunk.text])
    store.add([chunk], vectors)

    retriever = Retriever(embedder, store, top_k=1)
    results = retriever("some text")
    assert results[0].chunk_id == "c1"
    assert results[0].document_id == "doc-42"
    assert results[0].url == "http://x/doc-42"
    assert results[0].title == "Title"


def test_retriever_empty_store_returns_empty_list():
    embedder = HashingEmbedder(dimensions=8)
    store = InMemoryVectorStore()
    retriever = Retriever(embedder, store, top_k=5)
    results = retriever("anything")
    assert results == []


def test_retriever_min_score_filters_low_scoring_results():
    """A plain nearest-neighbor search always returns its top_k closest
    matches even when none are relevant -- min_score is what turns
    "least-bad match" into "no relevant results.\""""
    embedder = HashingEmbedder(dimensions=16)
    store = InMemoryVectorStore()
    chunk = _chunk("c1", "completely unrelated content about astronomy")
    vectors = embedder.embed_documents([chunk.text])
    store.add([chunk], vectors)

    unfiltered = Retriever(embedder, store, top_k=5, min_score=None)
    assert len(unfiltered("cooking recipes")) == 1  # returns the only chunk regardless of relevance

    filtered = Retriever(embedder, store, top_k=5, min_score=0.99)
    assert filtered("cooking recipes") == []  # unrelated query filtered out by the high threshold


def test_retriever_min_score_keeps_high_scoring_results():
    embedder = HashingEmbedder(dimensions=16)
    store = InMemoryVectorStore()
    chunk = _chunk("c1", "exact matching text content")
    vectors = embedder.embed_documents([chunk.text])
    store.add([chunk], vectors)

    retriever = Retriever(embedder, store, top_k=5, min_score=0.5)
    results = retriever("exact matching text content")
    assert len(results) == 1  # an exact-text query should score well above 0.5
