"""Reciprocal Rank Fusion (RRF): a deterministic, rank-based fusion of
multiple rankings.

RRF operates on rankings of ids, not documents or scores -- it knows
nothing about Document, Chunk, embeddings, vector stores, or providers.
This keeps it usable to fuse any two (or more) orderings, regardless of
what produced them (dense retrieval, lexical retrieval, a reranker, or
anything else a consumer builds).
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Sequence
from typing import TypeVar

from ragtorch.retrieval.bm25 import RankedItem

T = TypeVar("T", bound=Hashable)


def rrf(
    rankings: Iterable[Sequence[T]],
    *,
    k: int = 60,
    top_k: int | None = None,
) -> list[RankedItem[T]]:
    """Fuse multiple rankings of ids using Reciprocal Rank Fusion.

    RRF(d) = sum(1 / (k + rank)) across every ranking d appears in,
    with ranks 1-based. If an item appears more than once within a
    single ranking, only its first occurrence counts -- duplicate
    entries in one ranking do not grant extra votes.

    Deterministic tie-break: descending fused score, then first-seen
    order across the supplied rankings (in ranking order, then
    within-ranking rank order) -- this avoids requiring ids to be
    orderable, only hashable.
    """
    if k <= 0:
        raise ValueError(f"k must be > 0, got {k}")
    if top_k is not None and top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    scores: dict[T, float] = {}
    first_seen_order: dict[T, int] = {}
    counter = 0

    for ranking in rankings:
        seen_in_this_ranking: set[T] = set()
        for rank_minus_one, item in enumerate(ranking):
            if item in seen_in_this_ranking:
                continue
            seen_in_this_ranking.add(item)

            rank = rank_minus_one + 1
            scores[item] = scores.get(item, 0.0) + 1 / (k + rank)

            if item not in first_seen_order:
                first_seen_order[item] = counter
                counter += 1

    fused = [RankedItem(item=item, score=score) for item, score in scores.items()]
    fused.sort(key=lambda r: (-r.score, first_seen_order[r.item]))

    if top_k is not None:
        fused = fused[:top_k]
    return fused
