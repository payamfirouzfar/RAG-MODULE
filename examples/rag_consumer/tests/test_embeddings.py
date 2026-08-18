"""Embedding tests: dimension consistency, document/query embedding
shape. Uses HashingEmbedder (no model download, no GPU, no network)."""

from __future__ import annotations

from src.embeddings import HashingEmbedder


def test_embed_documents_returns_correct_dimensions():
    embedder = HashingEmbedder(dimensions=16)
    vectors = embedder.embed_documents(["hello world", "another text"])
    assert len(vectors) == 2
    assert all(len(v) == 16 for v in vectors)


def test_embed_query_returns_correct_dimensions():
    embedder = HashingEmbedder(dimensions=16)
    vector = embedder.embed_query("a query")
    assert len(vector) == 16


def test_embed_documents_empty_list():
    embedder = HashingEmbedder(dimensions=16)
    assert embedder.embed_documents([]) == []


def test_embed_query_and_embed_documents_are_consistent():
    embedder = HashingEmbedder(dimensions=16)
    (doc_vector,) = embedder.embed_documents(["same text"])
    query_vector = embedder.embed_query("same text")
    assert doc_vector == query_vector


def test_different_texts_produce_different_vectors():
    embedder = HashingEmbedder(dimensions=32)
    v1 = embedder.embed_query("cats and dogs")
    v2 = embedder.embed_query("quantum physics")
    assert v1 != v2
