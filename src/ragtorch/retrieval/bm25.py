"""BM25: a dependency-free, in-memory lexical retrieval index.

This is a deterministic scoring algorithm, not an executable component
-- it has no execution identity, lifecycle, or provider concept, so it
is deliberately NOT a Module (see the retrieval package's own
docstring for the full reasoning). It is appropriate for small/local
corpora and as a provider-independent primitive; it is not claimed to
be a distributed production search backend (no sharding, no
persistence, no incremental indexing in this version).
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T", bound=Hashable)

_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def default_tokenizer(text: str) -> Sequence[str]:
    """Case-folds and extracts word-like tokens. Deterministic, stdlib
    only (`re`). Callers needing stemming, language-specific rules, or
    domain-specific normalization should supply their own tokenizer --
    those concerns are deliberately not built into this default."""
    return _TOKEN_PATTERN.findall(text.lower())


@dataclass(frozen=True)
class RankedItem(Generic[T]):
    """A single ranked result: the item's identity plus its score.

    Deliberately not Document/Chunk/RetrievalResult -- those are
    consumer/application types. RankedItem only ever carries a
    caller-supplied, hashable identity and a float score.
    """

    item: T
    score: float


class BM25Index(Generic[T]):
    """A small in-memory inverted-index BM25 implementation.

    Constructed once from a fixed mapping of document id -> text, then
    searched. No mutation methods in this version -- if incremental
    indexing is ever needed, that is a separate design decision (a new
    method or a new class), not something to retrofit silently onto
    this immutable-after-construction model.
    """

    def __init__(
        self,
        documents: Mapping[T, str],
        *,
        tokenizer: Callable[[str], Sequence[str]] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if k1 < 0:
            raise ValueError(f"k1 must be >= 0, got {k1}")
        if not (0 <= b <= 1):
            raise ValueError(f"b must be in [0, 1], got {b}")

        self._k1 = k1
        self._b = b
        self._tokenizer = tokenizer or default_tokenizer

        # Insertion order is the deterministic tie-break for equal
        # scores -- captured here since dict/Mapping iteration order is
        # already insertion order in Python, but we pin it explicitly
        # rather than relying on that being obvious to a future reader.
        self._doc_ids: list[T] = list(documents.keys())
        self._doc_order: dict[T, int] = {doc_id: i for i, doc_id in enumerate(self._doc_ids)}

        self._doc_lengths: dict[T, int] = {}
        # token -> {doc_id: term_frequency}
        self._postings: dict[str, dict[T, int]] = defaultdict(dict)

        total_length = 0
        for doc_id, text in documents.items():
            tokens = self._tokenizer(text)
            self._doc_lengths[doc_id] = len(tokens)
            total_length += len(tokens)

            term_counts: dict[str, int] = defaultdict(int)
            for token in tokens:
                term_counts[token] += 1
            for token, count in term_counts.items():
                self._postings[token][doc_id] = count

        self._n_docs = len(self._doc_ids)
        self._avgdl = (total_length / self._n_docs) if self._n_docs else 0.0

    def search(self, query: str, *, top_k: int = 5) -> list[RankedItem[T]]:
        if top_k < 1:
            raise ValueError(f"top_k must be >= 1, got {top_k}")

        if self._n_docs == 0:
            return []

        query_tokens = self._tokenizer(query)
        scores: dict[T, float] = defaultdict(float)

        for token in query_tokens:
            postings = self._postings.get(token)
            if not postings:
                continue

            df = len(postings)
            idf = math.log(1 + (self._n_docs - df + 0.5) / (df + 0.5))

            for doc_id, tf in postings.items():
                doc_len = self._doc_lengths[doc_id]
                denominator = tf + self._k1 * (
                    1 - self._b + self._b * doc_len / self._avgdl if self._avgdl else 1
                )
                scores[doc_id] += idf * tf * (self._k1 + 1) / denominator

        ranked = [RankedItem(item=doc_id, score=score) for doc_id, score in scores.items()]
        ranked.sort(key=lambda r: (-r.score, self._doc_order[r.item]))
        return ranked[:top_k]
