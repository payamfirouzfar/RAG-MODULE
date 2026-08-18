"""VectorStore tests: insert, search, save/load. Uses InMemoryVectorStore
(no faiss dependency required for CI)."""

from __future__ import annotations

from pathlib import Path

from src.chunking import Chunk
from src.vector_store import InMemoryVectorStore


def _chunk(chunk_id: str, text: str = "some text") -> Chunk:
    return Chunk(
        chunk_id=chunk_id, document_id="d1", url="http://x", title="T", text=text, chunk_index=0
    )


def test_insert_and_search_returns_results():
    store = InMemoryVectorStore()
    store.add([_chunk("c1"), _chunk("c2")], [[1.0, 0.0], [0.0, 1.0]])
    results = store.search([1.0, 0.0], top_k=2)
    assert len(results) == 2
    assert results[0].chunk.chunk_id == "c1"  # exact match should rank first


def test_search_orders_by_score_descending():
    store = InMemoryVectorStore()
    store.add(
        [_chunk("close"), _chunk("far")],
        [[0.9, 0.1], [0.1, 0.9]],
    )
    results = store.search([1.0, 0.0], top_k=2)
    assert results[0].score >= results[1].score


def test_search_respects_top_k():
    store = InMemoryVectorStore()
    store.add([_chunk(f"c{i}") for i in range(5)], [[1.0, float(i)] for i in range(5)])
    results = store.search([1.0, 0.0], top_k=2)
    assert len(results) == 2


def test_search_on_empty_store_returns_empty_list():
    store = InMemoryVectorStore()
    assert store.search([1.0, 0.0], top_k=5) == []


def test_add_mismatched_lengths_raises():
    import pytest

    store = InMemoryVectorStore()
    with pytest.raises(ValueError):
        store.add([_chunk("c1")], [[1.0, 0.0], [0.0, 1.0]])


def test_save_and_load_round_trip(tmp_path: Path):
    store = InMemoryVectorStore()
    store.add([_chunk("c1", "text one"), _chunk("c2", "text two")], [[1.0, 0.0], [0.0, 1.0]])
    path = tmp_path / "store.json"
    store.save(path)

    loaded = InMemoryVectorStore()
    loaded.load(path)
    results = loaded.search([1.0, 0.0], top_k=2)
    assert results[0].chunk.chunk_id == "c1"
