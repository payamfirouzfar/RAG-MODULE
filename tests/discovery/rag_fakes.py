"""Step 27 discovery fakes: a deterministic, provider-independent toy RAG
pipeline used purely to generate evidence about what data contracts and
architectural boundaries a real RAG consumer would actually need.

None of this is production ragtorch API. Everything here is intentionally
private/test-local (see Step 27's Phase 11 "public API rule": nothing is
exported merely because it was useful in the experiment).

No network. No API key. No external model. No vector database. No
third-party AI dependency -- every "provider" here is a deterministic,
local, swappable Python object, used specifically to test whether the
pipeline shape leaks provider-specific assumptions anywhere.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

# ---------------------------------------------------------------------------
# Phase 3 candidate data contracts.
#
# Each type below is deliberately minimal and immutable (frozen dataclass)
# unless a concrete need for mutability was found. Fields were added only
# when a real stage in the pipeline needed to read or write them -- not
# speculatively.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Document:
    """A single unit of source content before chunking.

    id: needed so retrieval results can be traced back to a source
        (citation/debugging), independent of content equality.
    text: the only required payload for a text-only pipeline.
    metadata: an open dict so callers can attach arbitrary provenance
        (e.g. filename, url, page number) without the contract needing to
        know about every possible field in advance -- kept minimal on
        purpose, see Phase 3 notes in the evaluation ledger for why a
        typed metadata schema was rejected.
    """

    id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Chunk:
    """A retrievable unit derived from a Document.

    document_id: preserves traceability back to the source Document
        without embedding the whole Document (which could be large).
    """

    id: str
    document_id: str
    text: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Embedding:
    """A vector representation of a Chunk's text.

    chunk_id: which Chunk this vector represents.
    vector: a plain tuple of floats -- deliberately not tied to any
        specific dimensionality or provider's array type (e.g. no numpy
        dependency), so swapping embedding providers cannot be blocked by
        this type itself only by whatever downstream code assumes a fixed
        dimensionality (tested explicitly in Phase 4/6 below).
    """

    chunk_id: str
    vector: tuple[float, ...]


@dataclass(frozen=True)
class ScoredChunk:
    """A Chunk plus its retrieval score against a specific query."""

    chunk: Chunk
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    """The outcome of one retrieval call: the query plus ranked chunks.

    Deliberately holds an ordered tuple (not a dict/set) since rank order
    is itself meaningful retrieval output.
    """

    query: str
    scored_chunks: tuple[ScoredChunk, ...]


@dataclass(frozen=True)
class GenerationResult:
    """The outcome of a generation call: text plus which chunks fed it.

    source_chunk_ids: preserves citation/source-tracking ability without
        requiring the Generator itself to know about Document/Chunk
        internals -- assembled by the caller (PromptBuilder/pipeline),
        not the Generator.
    """

    text: str
    source_chunk_ids: tuple[str, ...]


# ---------------------------------------------------------------------------
# Phase 2/4 deterministic fake providers, each behind a narrow Protocol so
# they can be swapped independently (Phase 4's provider-boundary
# experiment). These Protocols are intentionally *not* built on
# ragtorch.core.Component -- see the evaluation ledger's Phase 4/5 notes
# for why forcing every stage through Module.__call__'s single-input/
# single-output shape was tried and rejected for some stages (embedding is
# naturally a batch operation, not a 1:1 call).
# ---------------------------------------------------------------------------


class Chunker(Protocol):
    def __call__(self, document: Document) -> list[Chunk]: ...


class Embedder(Protocol):
    def __call__(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class VectorStore(Protocol):
    def add(self, embeddings: list[Embedding], chunks: list[Chunk]) -> None: ...
    def search(self, query_vector: tuple[float, ...], top_k: int) -> list[ScoredChunk]: ...


class Retriever(Protocol):
    def __call__(self, query: str, *, top_k: int = 2) -> RetrievalResult: ...


class PromptBuilder(Protocol):
    def __call__(self, query: str, retrieval: RetrievalResult) -> str: ...


class Generator(Protocol):
    def __call__(self, prompt: str, retrieval: RetrievalResult) -> GenerationResult: ...


# ---------------------------------------------------------------------------
# Concrete deterministic fakes.
# ---------------------------------------------------------------------------


class FakeChunker:
    """Splits a Document into fixed-size word chunks. No real NLP."""

    def __init__(self, words_per_chunk: int = 6) -> None:
        self._words_per_chunk = words_per_chunk

    def __call__(self, document: Document) -> list[Chunk]:
        words = document.text.split()
        chunks = []
        for i in range(0, len(words), self._words_per_chunk):
            piece = " ".join(words[i : i + self._words_per_chunk])
            chunk_id = f"{document.id}::chunk{i // self._words_per_chunk}"
            chunks.append(Chunk(id=chunk_id, document_id=document.id, text=piece))
        return chunks


class HashingEmbedder:
    """Deterministic bag-of-words hashing embedder -- fixed dimensionality.

    Used as "Embedder A" in the provider-replacement experiment (Phase 4).
    """

    def __init__(self, dimensions: int = 16) -> None:
        self._dimensions = dimensions

    def __call__(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self._dimensions
            for word in text.lower().split():
                vec[hash(word) % self._dimensions] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append(tuple(v / norm for v in vec))
        return vectors


class CountingEmbedder:
    """A second, independent embedder with a DIFFERENT dimensionality and
    a different algorithm (character trigram counts, not word hashing).
    Used as "Embedder B" to prove the pipeline does not assume a fixed
    embedding dimensionality anywhere (Phase 4/6)."""

    def __init__(self, dimensions: int = 8) -> None:
        self._dimensions = dimensions

    def __call__(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = []
        for text in texts:
            vec = [0.0] * self._dimensions
            lowered = text.lower()
            for i in range(len(lowered) - 2):
                trigram = lowered[i : i + 3]
                vec[hash(trigram) % self._dimensions] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append(tuple(v / norm for v in vec))
        return vectors


class InMemoryVectorStore:
    """Cosine-similarity search over an in-memory list. "Store A"."""

    def __init__(self) -> None:
        self._embeddings: list[Embedding] = []
        self._chunks_by_id: dict[str, Chunk] = {}

    def add(self, embeddings: list[Embedding], chunks: list[Chunk]) -> None:
        self._embeddings.extend(embeddings)
        for chunk in chunks:
            self._chunks_by_id[chunk.id] = chunk

    def search(self, query_vector: tuple[float, ...], top_k: int) -> list[ScoredChunk]:
        scored = []
        for emb in self._embeddings:
            if len(emb.vector) != len(query_vector):
                raise ValueError(
                    f"dimensionality mismatch: store has {len(emb.vector)}-dim vectors, "
                    f"query is {len(query_vector)}-dim"
                )
            score = _cosine_similarity(emb.vector, query_vector)
            scored.append(ScoredChunk(chunk=self._chunks_by_id[emb.chunk_id], score=score))
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_k]


class InvertedIndexVectorStore:
    """A SECOND, independent store implementation -- not vector-based at
    all, a plain keyword inverted index -- used to prove the Retriever
    contract does not assume "vector store" as the only possible retrieval
    mechanism (Phase 4/6, "hybrid retrieval" adversarial case)."""

    def __init__(self) -> None:
        self._chunks: list[Chunk] = []

    def add(self, embeddings: list[Embedding], chunks: list[Chunk]) -> None:
        # Deliberately ignores embeddings entirely -- proves a VectorStore
        # implementation is not required to be vector-based at all, only
        # to satisfy the add/search shape.
        self._chunks.extend(chunks)

    def search(self, query_vector: tuple[float, ...], top_k: int) -> list[ScoredChunk]:
        # query_vector is unused; this store ranks by keyword overlap
        # instead. Included only to prove the Protocol shape does not
        # force a vector-similarity implementation.
        raise NotImplementedError(
            "InvertedIndexVectorStore intentionally cannot implement vector "
            "search -- see search_by_keywords() -- proving VectorStore's "
            "search(query_vector, top_k) signature already assumes a "
            "vector-based retrieval strategy and is not truly retrieval-"
            "mechanism-agnostic (see Phase 6 adversarial finding)."
        )

    def search_by_keywords(self, query: str, top_k: int) -> list[ScoredChunk]:
        query_words = set(query.lower().split())
        scored = []
        for chunk in self._chunks:
            overlap = len(query_words & set(chunk.text.lower().split()))
            if overlap > 0:
                scored.append(ScoredChunk(chunk=chunk, score=float(overlap)))
        scored.sort(key=lambda sc: sc.score, reverse=True)
        return scored[:top_k]


def _cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a)) or 1.0
    norm_b = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (norm_a * norm_b)


class SimpleRetriever:
    """Wires an Embedder + VectorStore into the Retriever shape."""

    def __init__(self, embedder: Embedder, store: InMemoryVectorStore) -> None:
        self._embedder = embedder
        self._store = store

    def __call__(self, query: str, *, top_k: int = 2) -> RetrievalResult:
        (query_vector,) = self._embedder([query])
        scored_chunks = tuple(self._store.search(query_vector, top_k))
        return RetrievalResult(query=query, scored_chunks=scored_chunks)


class KeywordRetriever:
    """A retriever that does not use embeddings at all -- proves the
    Retriever Protocol itself does not require an Embedder/VectorStore
    dependency, only the __call__(query, top_k) -> RetrievalResult shape."""

    def __init__(self, store: InvertedIndexVectorStore) -> None:
        self._store = store

    def __call__(self, query: str, *, top_k: int = 2) -> RetrievalResult:
        scored_chunks = tuple(self._store.search_by_keywords(query, top_k))
        return RetrievalResult(query=query, scored_chunks=scored_chunks)


class SimplePromptBuilder:
    def __call__(self, query: str, retrieval: RetrievalResult) -> str:
        context = "\n".join(sc.chunk.text for sc in retrieval.scored_chunks)
        return f"Context:\n{context}\n\nQuestion: {query}\nAnswer:"


class EchoGenerator:
    """Generator A: deterministic, no real language model. Concatenates
    retrieved chunk text into a canned answer shape."""

    def __call__(self, prompt: str, retrieval: RetrievalResult) -> GenerationResult:
        chunk_texts = [sc.chunk.text for sc in retrieval.scored_chunks]
        text = f"Based on {len(chunk_texts)} sources: " + " | ".join(chunk_texts)
        source_ids = tuple(sc.chunk.id for sc in retrieval.scored_chunks)
        return GenerationResult(text=text, source_chunk_ids=source_ids)


class WordCountGenerator:
    """Generator B: a completely different deterministic strategy
    (reports word counts instead of echoing text), used to prove the
    pipeline does not depend on EchoGenerator's specific output shape,
    only the Generator Protocol's __call__(prompt, retrieval) ->
    GenerationResult signature."""

    def __call__(self, prompt: str, retrieval: RetrievalResult) -> GenerationResult:
        counts = Counter()
        for sc in retrieval.scored_chunks:
            counts[sc.chunk.id] = len(sc.chunk.text.split())
        text = ", ".join(f"{cid}: {n} words" for cid, n in counts.items())
        source_ids = tuple(sc.chunk.id for sc in retrieval.scored_chunks)
        return GenerationResult(text=text, source_chunk_ids=source_ids)


class FailingEmbedder:
    """Always raises -- used for provider-failure-propagation tests."""

    def __call__(self, texts: list[str]) -> list[tuple[float, ...]]:
        raise RuntimeError("embedding provider unavailable")


class FailingGenerator:
    """Always raises -- used for provider-failure-propagation tests."""

    def __call__(self, prompt: str, retrieval: RetrievalResult) -> GenerationResult:
        raise RuntimeError("generation provider unavailable")


# ---------------------------------------------------------------------------
# The complete pipeline, wiring every stage together as plain function
# calls -- deliberately NOT using ragtorch.core.Sequential/Module here
# first, so the experiment can separately determine (a) whether the
# pipeline works at all with plain Python, and (b) whether wrapping it in
# Module/Sequential adds friction or fits naturally (tested separately in
# test_rag_consumer.py).
# ---------------------------------------------------------------------------


def run_pipeline(
    documents: list[Document],
    *,
    chunker: Chunker,
    embedder: Embedder,
    store: InMemoryVectorStore,
    retriever_factory: type[SimpleRetriever] = SimpleRetriever,
    prompt_builder: PromptBuilder,
    generator: Generator,
    query: str,
    top_k: int = 2,
) -> GenerationResult:
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunker(document))

    vectors = embedder([c.text for c in chunks])
    embeddings = [Embedding(chunk_id=c.id, vector=v) for c, v in zip(chunks, vectors, strict=True)]
    store.add(embeddings, chunks)

    retriever = retriever_factory(embedder, store)
    retrieval = retriever(query, top_k=top_k)

    prompt = prompt_builder(query, retrieval)
    return generator(prompt, retrieval)
