"""Application-level vector store. NOT part of ragtorch.

Two implementations satisfying the same VectorStore Protocol:
- FaissVectorStore: real, FAISS-backed, cosine similarity via inner
  product on L2-normalized vectors, with save()/load().
- InMemoryVectorStore: dependency-free fallback for unit tests.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .chunking import Chunk


@dataclass(frozen=True)
class ScoredChunk:
    chunk: Chunk
    score: float


class VectorStore(Protocol):
    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]: ...
    def save(self, path: Path) -> None: ...
    def load(self, path: Path) -> None: ...


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


class InMemoryVectorStore:
    """Dependency-free cosine-similarity search over a Python list.
    Used in unit tests and as a fallback when faiss is unavailable."""

    def __init__(self) -> None:
        self._vectors: list[list[float]] = []
        self._chunks: list[Chunk] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        self._chunks.extend(chunks)
        self._vectors.extend(_normalize(v) for v in vectors)

    def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        if not self._vectors:
            return []
        query = _normalize(query_vector)
        scored = [
            ScoredChunk(chunk=chunk, score=sum(a * b for a, b in zip(query, vec, strict=True)))
            for chunk, vec in zip(self._chunks, self._vectors, strict=True)
        ]
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_k]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "vectors": self._vectors,
            "chunks": [c.to_dict() for c in self._chunks],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def load(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        self._vectors = payload["vectors"]
        self._chunks = [Chunk(**c) for c in payload["chunks"]]


class FaissVectorStore:
    """Real vector index using FAISS (IndexFlatIP over L2-normalized
    vectors == cosine similarity). Requires the optional `faiss-cpu`
    dependency (this demo's requirements.txt only, never ragtorch's)."""

    def __init__(self, dimensions: int) -> None:
        try:
            import faiss
        except ImportError as e:
            raise ImportError(
                "faiss-cpu is required for FaissVectorStore. Install it with: pip install faiss-cpu"
            ) from e
        self._faiss = faiss
        self.dimensions = dimensions
        self._index = faiss.IndexFlatIP(dimensions)
        self._chunks: list[Chunk] = []

    def add(self, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        import numpy as np

        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        if not chunks:
            return
        matrix = np.array([_normalize(v) for v in vectors], dtype="float32")
        self._index.add(matrix)
        self._chunks.extend(chunks)

    def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        import numpy as np

        if self._index.ntotal == 0:
            return []
        query = np.array([_normalize(query_vector)], dtype="float32")
        scores, indices = self._index.search(query, min(top_k, self._index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0], strict=True):
            if idx < 0:
                continue
            results.append(ScoredChunk(chunk=self._chunks[idx], score=float(score)))
        return results

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._faiss.write_index(self._index, str(path.with_suffix(".faiss")))
        meta_path = path.with_suffix(".meta.json")
        meta_path.write_text(
            json.dumps(
                {"chunks": [c.to_dict() for c in self._chunks], "dimensions": self.dimensions}
            ),
            encoding="utf-8",
        )

    def load(self, path: Path) -> None:
        self._index = self._faiss.read_index(str(path.with_suffix(".faiss")))
        meta = json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))
        self._chunks = [Chunk(**c) for c in meta["chunks"]]
        self.dimensions = meta["dimensions"]


def build_vector_store(backend: str, *, dimensions: int) -> VectorStore:
    if backend == "faiss":
        return FaissVectorStore(dimensions)
    if backend == "in_memory":
        return InMemoryVectorStore()
    raise ValueError(f"unknown vector_store_backend: {backend!r}")
