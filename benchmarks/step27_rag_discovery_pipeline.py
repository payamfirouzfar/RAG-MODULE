"""Step 27 benchmark: measure each stage of the deterministic discovery
RAG pipeline (tests/discovery/rag_fakes.py) separately, plus the whole
pipeline end to end.

Run from the repository root with:
    python benchmarks/step27_rag_discovery_pipeline.py

Purpose: identify where accidental architecture overhead exists (if any)
before any real contract is designed -- not to characterize real-world
RAG performance, since every stage here is a deterministic local fake,
not a real embedding model, vector database, or LLM. Real provider
latency will overwhelmingly dominate any of these numbers once real
providers exist; this benchmark exists only to catch the framework's
own overhead, matching this project's established benchmark discipline
(see e.g. step18/step23) of measuring, never asserting a threshold.

No network. No API key. No external model. No vector database. No
third-party AI dependency.
"""

from __future__ import annotations

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.discovery.rag_fakes import (
    Chunk,
    Document,
    EchoGenerator,
    Embedding,
    HashingEmbedder,
    InMemoryVectorStore,
    SimplePromptBuilder,
    SimpleRetriever,
)

DOCS = [
    Document(
        id=f"doc-{i}",
        text=f"Document number {i} about retrieval augmented generation topic {i % 7}.",
    )
    for i in range(50)
]


def _time_it(fn, iterations: int = 200) -> tuple[float, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.mean(samples), statistics.median(samples)


def _report(label: str, mean_ms: float, median_ms: float) -> None:
    print(f"{label:40s} mean={mean_ms:9.4f}ms  median={median_ms:9.4f}ms")


def main() -> None:
    chunker = lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)]  # noqa: E731
    embedder = HashingEmbedder(dimensions=16)

    print("Step 27 discovery pipeline benchmark (deterministic fakes only)\n")

    mean, median = _time_it(lambda: [chunker(d) for d in DOCS])
    _report("chunking (50 docs)", mean, median)

    chunks = [c for d in DOCS for c in chunker(d)]
    texts = [c.text for c in chunks]
    mean, median = _time_it(lambda: embedder(texts))
    _report("embedding (50 chunks, 16-dim)", mean, median)

    vectors = embedder(texts)
    embeddings = [Embedding(chunk_id=c.id, vector=v) for c, v in zip(chunks, vectors, strict=True)]

    def build_store() -> InMemoryVectorStore:
        store = InMemoryVectorStore()
        store.add(embeddings, chunks)
        return store

    mean, median = _time_it(build_store)
    _report("indexing (50 chunks into store)", mean, median)

    store = build_store()
    retriever = SimpleRetriever(embedder, store)
    mean, median = _time_it(lambda: retriever("retrieval augmented generation", top_k=5))
    _report("retrieval (50-chunk store, top_k=5)", mean, median)

    retrieval = retriever("retrieval augmented generation", top_k=5)
    prompt_builder = SimplePromptBuilder()
    mean, median = _time_it(lambda: prompt_builder("retrieval augmented generation", retrieval))
    _report("prompt construction", mean, median)

    generator = EchoGenerator()
    prompt = prompt_builder("retrieval augmented generation", retrieval)
    mean, median = _time_it(lambda: generator(prompt, retrieval))
    _report("generation (fake, no real model)", mean, median)

    def full_pipeline() -> None:
        local_chunks = [c for d in DOCS for c in chunker(d)]
        local_texts = [c.text for c in local_chunks]
        local_vectors = embedder(local_texts)
        local_embeddings = [
            Embedding(chunk_id=c.id, vector=v)
            for c, v in zip(local_chunks, local_vectors, strict=True)
        ]
        local_store = InMemoryVectorStore()
        local_store.add(local_embeddings, local_chunks)
        local_retriever = SimpleRetriever(embedder, local_store)
        local_retrieval = local_retriever("retrieval augmented generation", top_k=5)
        local_prompt = prompt_builder("retrieval augmented generation", local_retrieval)
        generator(local_prompt, local_retrieval)

    mean, median = _time_it(full_pipeline, iterations=50)
    _report("complete pipeline (50 docs, cold index)", mean, median)

    print(
        "\nNo threshold asserted. This measures the discovery fakes' own "
        "overhead only -- real embedding/LLM provider latency will "
        "dominate all of these numbers once real providers exist."
    )


if __name__ == "__main__":
    main()
