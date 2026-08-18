"""Step 32 benchmark: BM25Index build/search and rrf fusion time at
three corpus sizes.

Purpose: understand the implementation's actual scaling
characteristics, not to establish a hard threshold. This is a
dependency-free in-memory index -- it is NOT claimed to be a
distributed production search backend (no sharding, no persistence).
Run from the repository root with:

    python benchmarks/step32_bm25_rrf.py

No network. No provider. No GPU.
"""

from __future__ import annotations

import statistics
import time

from ragtorch.retrieval import BM25Index, rrf

CORPUS_SIZES = (100, 1_000, 10_000)

_WORDS = [
    "python",
    "programming",
    "language",
    "database",
    "index",
    "retrieval",
    "vector",
    "search",
    "document",
    "query",
    "ranking",
    "algorithm",
    "text",
    "data",
    "system",
]


def _make_corpus(n: int) -> dict[str, str]:
    return {
        f"doc-{i}": " ".join(_WORDS[j % len(_WORDS)] for j in range(i, i + 20)) for i in range(n)
    }


def _time_it(fn, iterations: int) -> tuple[float, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)  # milliseconds
    return statistics.mean(samples), statistics.median(samples)


def main() -> None:
    print("Step 32 BM25 + RRF benchmark\n")
    print(f"{'operation':40s} {'mean (ms)':>12s} {'median (ms)':>12s}")

    for n in CORPUS_SIZES:
        corpus = _make_corpus(n)
        build_iterations = 20 if n <= 1_000 else 3

        mean, median = _time_it(
            lambda corpus=corpus: BM25Index(corpus), iterations=build_iterations
        )
        print(f"{'BM25 build, n=' + str(n):40s} {mean:12.3f} {median:12.3f}")

        index = BM25Index(corpus)
        search_iterations = 200 if n <= 1_000 else 50
        mean, median = _time_it(
            lambda index=index: index.search("python programming retrieval"),
            iterations=search_iterations,
        )
        print(f"{'BM25 search, n=' + str(n):40s} {mean:12.4f} {median:12.4f}")
        print()

    print("RRF fusion (two rankings, varying length):\n")
    for n in (10, 100, 1_000):
        ranking1 = [f"doc-{i}" for i in range(n)]
        ranking2 = [f"doc-{(i * 7) % n}" for i in range(n)]
        mean, median = _time_it(lambda r1=ranking1, r2=ranking2: rrf([r1, r2]), iterations=200)
        print(f"{'rrf, ranking length=' + str(n):40s} {mean:12.4f} {median:12.4f}")

    print(
        "\nNo threshold asserted. BM25Index.__init__ tokenizes and indexes "
        "every document once (O(total tokens)); search() only scores "
        "documents appearing in the query-term postings (not a full scan). "
        "rrf() is O(total items across all rankings). This is a "
        "dependency-free in-memory implementation appropriate for small/"
        "local corpora and as a provider-independent primitive -- it is "
        "not claimed to be a distributed production search backend."
    )


if __name__ == "__main__":
    main()
