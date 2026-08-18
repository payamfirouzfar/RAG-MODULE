"""retrieval: small, provider-independent retrieval primitives.

BM25Index (lexical retrieval) and rrf (deterministic rank fusion) are
deliberately plain Python -- not ragtorch.Module. Both are
deterministic indexing/scoring/ranking algorithms with no execution
identity, lifecycle, or provider concept; wrapping them as Modules
would add framework coupling with no evidence any consumer needs it
(see evaluation/step32-evaluation.md). A future consumer that actually
needs these as executable, lifecycle-bearing components can wrap them
in an application-level adapter -- exactly the pattern
examples/rag_consumer already uses for Retriever/Generator.

This package intentionally does not define Document, Chunk,
RetrievalResult, or any provider/embedding/vector-store type -- those
remain application-level concerns.
"""

from ragtorch.retrieval.bm25 import BM25Index, RankedItem, default_tokenizer
from ragtorch.retrieval.fusion import rrf

__all__ = [
    "BM25Index",
    "RankedItem",
    "default_tokenizer",
    "rrf",
]
