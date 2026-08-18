"""Benchmark for the RAG consumer demo: chunking, embedding, indexing,
retrieval, and (if MODE="llm" and an API key is configured) generation
latency.

No hard performance threshold is asserted -- this measures and reports,
matching ragtorch's own established benchmark discipline (see
benchmarks/step*.py in the main repository). Run with:

    python benchmark.py

Uses HashingEmbedder + InMemoryVectorStore by default (no model
download required) so this benchmark is runnable without GPU/network.
Pass --real-embedder to use SentenceTransformersEmbedder instead
(requires sentence-transformers to be installed).
"""

from __future__ import annotations

import argparse
import statistics
import time

from src.chunking import chunk_documents
from src.config import DEFAULT_CONFIG
from src.dataset import Document
from src.embeddings import HashingEmbedder
from src.generator import OfflineGenerator
from src.pipeline import build_pipeline, run_pipeline
from src.retriever import Retriever
from src.vector_store import InMemoryVectorStore

SAMPLE_DOCUMENTS = [
    Document(
        document_id=f"doc-{i}",
        url=f"http://example.com/{i}",
        title=f"Document {i}",
        text=(
            f"This is sample document number {i}. It discusses topic {i % 5} "
            "in reasonable detail, covering background, examples, and a short "
            "conclusion. " * 5
        ),
        retrieved_at="2026-01-01",
    )
    for i in range(20)
]


def _time_it(fn, iterations: int = 20) -> tuple[float, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.mean(samples), statistics.median(samples)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--real-embedder", action="store_true")
    args = parser.parse_args()

    config = DEFAULT_CONFIG

    if args.real_embedder:
        from src.embeddings import SentenceTransformersEmbedder

        embedder = SentenceTransformersEmbedder(config.embedding_model)
    else:
        embedder = HashingEmbedder(dimensions=64)

    print("RAG consumer demo benchmark\n")
    print(f"embedder: {embedder.model_name}")
    print(f"documents: {len(SAMPLE_DOCUMENTS)}\n")

    mean, median = _time_it(
        lambda: chunk_documents(
            SAMPLE_DOCUMENTS, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
        ),
        iterations=10,
    )
    print(f"{'chunking':30s} mean={mean:9.3f}ms  median={median:9.3f}ms")

    chunks = chunk_documents(
        SAMPLE_DOCUMENTS, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
    )
    print(f"{'  -> chunks produced':30s} {len(chunks)}")

    texts = [c.text for c in chunks]
    mean, median = _time_it(lambda: embedder.embed_documents(texts), iterations=5)
    print(f"{'embedding':30s} mean={mean:9.3f}ms  median={median:9.3f}ms")

    vectors = embedder.embed_documents(texts)

    def build_store():
        store = InMemoryVectorStore()
        store.add(chunks, vectors)
        return store

    mean, median = _time_it(build_store, iterations=10)
    print(f"{'indexing':30s} mean={mean:9.3f}ms  median={median:9.3f}ms")

    store = build_store()
    retriever = Retriever(embedder, store, top_k=config.top_k)
    mean, median = _time_it(lambda: retriever("sample query about topic 2"), iterations=20)
    print(f"{'retrieval':30s} mean={mean:9.3f}ms  median={median:9.3f}ms")

    generator = OfflineGenerator()
    pipeline = build_pipeline(
        retriever=retriever, reranker=None, generator=generator, mode="offline"
    )
    mean, median = _time_it(
        lambda: run_pipeline(pipeline, "sample query about topic 2"), iterations=20
    )
    print(f"{'complete pipeline (offline mode)':30s} mean={mean:9.3f}ms  median={median:9.3f}ms")

    print(
        "\nNo threshold asserted -- this measures the demo's own overhead. "
        "LLM generation latency is not included by default (requires a real "
        "API key and network access); run with MODE='llm' in the notebook "
        "to observe real generation latency."
    )


if __name__ == "__main__":
    main()
