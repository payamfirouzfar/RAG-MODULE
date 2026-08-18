"""Contract test: the ragtorch.retrieval public surface, imported the
same way ragtorch.evaluation already is -- a separate subpackage
import, not re-exported from top-level ragtorch.__all__."""

from __future__ import annotations

import ragtorch.retrieval


def test_retrieval_public_exports_present():
    assert set(ragtorch.retrieval.__all__) == {
        "BM25Index",
        "RankedItem",
        "default_tokenizer",
        "rrf",
    }


def test_documented_import_path_works():
    from ragtorch.retrieval import BM25Index, RankedItem, rrf

    assert BM25Index is not None
    assert RankedItem is not None
    assert rrf is not None
