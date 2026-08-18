"""Chunking tests: empty document, short document, long document,
overlap, deterministic IDs."""

from __future__ import annotations

import pytest
from src.chunking import chunk_document, chunk_documents
from src.dataset import Document


def _doc(text: str, document_id: str = "d1") -> Document:
    return Document(
        document_id=document_id, url="http://x", title="T", text=text, retrieved_at="2026-01-01"
    )


def test_empty_document_produces_zero_chunks():
    chunks = chunk_document(_doc(""), chunk_size=100, chunk_overlap=10)
    assert chunks == []


def test_short_document_produces_one_chunk():
    chunks = chunk_document(_doc("hello world"), chunk_size=100, chunk_overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_index == 0


def test_long_document_produces_multiple_chunks():
    text = "x" * 1000
    chunks = chunk_document(_doc(text), chunk_size=200, chunk_overlap=20)
    assert len(chunks) > 1
    assert all(len(c.text) <= 200 for c in chunks)


def test_chunk_overlap_produces_overlapping_text():
    text = "abcdefghij" * 20  # 200 chars
    chunks = chunk_document(_doc(text), chunk_size=50, chunk_overlap=10)
    assert len(chunks) > 1
    # the tail of chunk[0] should reappear at the head of chunk[1]
    assert chunks[0].text[-10:] == chunks[1].text[:10]


def test_chunk_ids_are_deterministic_across_calls():
    text = "some repeated content " * 30
    doc = _doc(text)
    chunks1 = chunk_document(doc, chunk_size=100, chunk_overlap=10)
    chunks2 = chunk_document(doc, chunk_size=100, chunk_overlap=10)
    assert [c.chunk_id for c in chunks1] == [c.chunk_id for c in chunks2]


def test_chunk_ids_are_unique_within_a_document():
    text = "some repeated content " * 30
    chunks = chunk_document(_doc(text), chunk_size=100, chunk_overlap=10)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))


def test_chunk_overlap_must_be_smaller_than_chunk_size():
    with pytest.raises(ValueError, match="chunk_overlap"):
        chunk_document(_doc("text"), chunk_size=50, chunk_overlap=50)


def test_chunk_metadata_preserved():
    doc = Document(
        document_id="d42",
        url="http://example.com/p",
        title="My Title",
        text="some content here",
        retrieved_at="2026-01-01",
    )
    chunks = chunk_document(doc, chunk_size=100, chunk_overlap=10)
    assert chunks[0].document_id == "d42"
    assert chunks[0].url == "http://example.com/p"
    assert chunks[0].title == "My Title"


def test_chunk_documents_across_multiple_documents():
    docs = [_doc("aaa" * 50, "d1"), _doc("bbb" * 50, "d2")]
    chunks = chunk_documents(docs, chunk_size=100, chunk_overlap=10)
    doc_ids = {c.document_id for c in chunks}
    assert doc_ids == {"d1", "d2"}
