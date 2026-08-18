"""BM25Index tests: human-readable relevance checks, top_k, empty/
unknown queries, parameter validation, deterministic ties."""

from __future__ import annotations

import pytest

from ragtorch.retrieval import BM25Index


def test_basic_relevance_returns_only_matching_documents():
    documents = {
        "d1": "the cat sat on the mat",
        "d2": "the dog sat on the rug",
        "d3": "the cat chased the mouse",
    }
    bm25 = BM25Index(documents)
    results = bm25.search("cat")

    assert {r.item for r in results} == {"d1", "d3"}
    assert all(r.score > 0 for r in results)
    # deterministic ordering: must not vary across repeated calls
    assert [r.item for r in results] == [r.item for r in bm25.search("cat")]


def test_relevance_ranks_more_specific_match_higher():
    documents = {
        "d1": "python programming language",
        "d2": "python snake animal",
        "d3": "database indexing",
    }
    bm25 = BM25Index(documents)
    results = bm25.search("python programming")

    ids = [r.item for r in results]
    assert ids.index("d1") < ids.index("d2")
    assert "d3" not in ids


def test_top_k_limits_result_count():
    documents = {
        "d1": "python programming",
        "d2": "python snake",
        "d3": "python database",
    }
    bm25 = BM25Index(documents)
    results = bm25.search("python", top_k=1)
    assert len(results) == 1


def test_unknown_query_returns_empty_list():
    documents = {"d1": "python programming language"}
    bm25 = BM25Index(documents)
    assert bm25.search("nonexistent") == []


def test_empty_index_returns_empty_list():
    bm25 = BM25Index({})
    assert bm25.search("anything") == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k1": -1.0},
        {"b": -0.1},
        {"b": 1.1},
    ],
)
def test_invalid_constructor_parameters_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        BM25Index({"d1": "text"}, **kwargs)


def test_invalid_top_k_raises_value_error():
    bm25 = BM25Index({"d1": "text"})
    with pytest.raises(ValueError):
        bm25.search("text", top_k=0)


def test_equal_scoring_documents_break_ties_by_insertion_order():
    # d1 and d2 have identical content -> identical BM25 scores;
    # insertion order (d1 before d2) must be the deterministic tie-break.
    documents = {
        "d1": "same content here",
        "d2": "same content here",
    }
    bm25 = BM25Index(documents)
    results = bm25.search("same content")
    assert results[0].score == results[1].score
    assert [r.item for r in results] == ["d1", "d2"]


def test_arbitrary_hashable_ids_are_supported():
    documents = {
        1: "python programming",
        ("two",): "snake animal",
    }
    bm25 = BM25Index(documents)
    results = bm25.search("python")
    assert results[0].item == 1


def test_mapping_prevents_duplicate_ids_by_construction():
    # A Python dict literal cannot contain a duplicate key -- the last
    # value silently wins, which is standard dict semantics, not a
    # BM25Index-specific behavior. This test documents that fact rather
    # than asserting BM25Index does its own duplicate-detection.
    documents = {"d1": "first version", "d1": "second version"}  # noqa: F601
    assert len(documents) == 1
    bm25 = BM25Index(documents)
    assert bm25.search("second") != []
    assert bm25.search("first") == []
