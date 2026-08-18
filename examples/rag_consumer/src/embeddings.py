"""Application-level embedding interface. NOT part of ragtorch.

Embedder is a Protocol so any implementation (sentence-transformers,
a hash-based fallback for tests, or a future provider) satisfies it
structurally -- swapping implementations never requires touching the
rest of the pipeline (Retriever/VectorStore/etc. only depend on this
Protocol's shape, never a concrete class).
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformersEmbedder:
    """Real embedding provider using the sentence-transformers library.
    Requires the optional `sentence-transformers` dependency (declared
    only in this demo's requirements.txt, never ragtorch's)."""

    def __init__(self, model_name: str) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "sentence-transformers is required for SentenceTransformersEmbedder. "
                "Install it with: pip install sentence-transformers"
            ) from e
        self._model = SentenceTransformer(model_name)
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        (vector,) = self.embed_documents([text])
        return vector


class HashingEmbedder:
    """Deterministic, dependency-free fallback embedder. Used in unit
    tests (no model download, no GPU, no network) and as a worked
    example of "EmbeddingProvider B" proving the pipeline is replaceable
    without depending on sentence-transformers at all."""

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions
        self.model_name = f"hashing-embedder-{dimensions}d"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).hexdigest()
            index = int(digest, 16) % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]
