"""Hybrid dense+lexical demonstration: the actual reason BM25Index and
rrf ship together. RRF only becomes useful when there are at least two
real rankings to fuse -- this test exercises exactly that."""

from __future__ import annotations

from ragtorch.retrieval import rrf


def test_hybrid_fusion_of_disagreeing_dense_and_lexical_rankings():
    # Two rankings that disagree on order and on which ids they even
    # contain -- a realistic disagreement between a dense retriever and
    # a lexical (BM25) retriever over the same query.
    dense = ["A", "C", "B"]
    lexical = ["B", "A", "D"]

    fused = rrf([dense, lexical])
    fused_ids = [r.item for r in fused]

    # Union of both rankings' ids must all be present.
    assert set(fused_ids) == {"A", "B", "C", "D"}

    # Deterministic: identical inputs always produce the identical order.
    assert fused_ids == [r.item for r in rrf([dense, lexical])]

    # A and B each appear in both rankings (reinforced by both signals)
    # and should outrank C/D, which each appear in only one ranking.
    assert fused_ids.index("A") < fused_ids.index("C")
    assert fused_ids.index("B") < fused_ids.index("D")
