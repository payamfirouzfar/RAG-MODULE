"""rrf tests: human-readable fusion checks, duplicate handling, empty
input, top_k, parameter validation, arbitrary hashable ids."""

from __future__ import annotations

import pytest

from ragtorch.retrieval import rrf


def test_basic_fusion_matches_worked_example():
    ranking1 = ["A", "B", "C"]
    ranking2 = ["B", "C", "A"]
    fused = rrf([ranking1, ranking2])

    assert fused[0].item == "B"
    # deterministic: repeated calls produce the identical order
    assert [r.item for r in fused] == [r.item for r in rrf([ranking1, ranking2])]


def test_fusion_scores_match_hand_computed_values():
    k = 60
    ranking1 = ["A", "B", "C"]
    ranking2 = ["B", "C", "A"]
    fused = {r.item: r.score for r in rrf([ranking1, ranking2], k=k)}

    assert fused["A"] == pytest.approx(1 / (k + 1) + 1 / (k + 3))
    assert fused["B"] == pytest.approx(1 / (k + 2) + 1 / (k + 1))
    assert fused["C"] == pytest.approx(1 / (k + 3) + 1 / (k + 2))


def test_duplicate_items_in_one_ranking_count_only_once():
    ranking = ["A", "A", "B"]
    fused = {r.item: r.score for r in rrf([ranking])}
    k = 60
    # A's FIRST occurrence is rank 1; the second "A" at rank 3 must not count.
    assert fused["A"] == pytest.approx(1 / (k + 1))
    assert fused["B"] == pytest.approx(1 / (k + 3))


def test_empty_rankings_list_returns_empty_list():
    assert rrf([]) == []


def test_rankings_containing_empty_sequences_are_valid():
    assert rrf([[], []]) == []
    assert rrf([[], ["A"]]) == [rrf([["A"]])[0]]


def test_top_k_limits_result_count():
    fused = rrf([["A", "B", "C"], ["C", "B", "A"]], top_k=2)
    assert len(fused) == 2


def test_invalid_k_raises_value_error():
    with pytest.raises(ValueError):
        rrf([["A"]], k=0)
    with pytest.raises(ValueError):
        rrf([["A"]], k=-1)


def test_invalid_top_k_raises_value_error():
    with pytest.raises(ValueError):
        rrf([["A"]], top_k=0)


def test_arbitrary_hashable_ids_not_required_to_be_orderable():
    ranking1 = [1, "two", ("three",)]
    ranking2 = [("three",), 1, "two"]
    fused = rrf([ranking1, ranking2])
    assert {r.item for r in fused} == {1, "two", ("three",)}


def test_tie_break_is_first_seen_order_across_rankings():
    # Every item appears in exactly one ranking at the same rank, so
    # all fused scores are equal -- tie-break must be first-seen order:
    # ranking order first, then within-ranking rank order.
    fused = rrf([["X"], ["Y"], ["Z"]])
    assert [r.item for r in fused] == ["X", "Y", "Z"]
