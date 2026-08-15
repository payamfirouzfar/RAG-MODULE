"""Performance baseline for Step 1. Records call overhead so future
optimizations (if ever needed) can be justified against real numbers.

Run: python evaluation/benchmark_baseline.py
"""

from __future__ import annotations

import time

from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class Identity(Module):
    def forward(self, input):
        return input


def timeit(fn, iterations: int = 20_000) -> dict[str, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1_000_000)  # microseconds
    samples.sort()
    n = len(samples)
    return {
        "p50": samples[int(n * 0.50)],
        "p95": samples[int(n * 0.95)],
        "p99": samples[int(n * 0.99)],
    }


def main() -> None:
    single = Identity()
    seq10 = Sequential(*[Identity() for _ in range(10)])
    parent = Identity()
    parent.inspect_target = seq10  # exercise attribute registration

    print("Module call overhead (single module):")
    print(timeit(lambda: single(1)))

    print("\nSequential (10 modules):")
    print(timeit(lambda: seq10(1)))

    print("\ninspect() on 11-module tree:")
    print(timeit(lambda: parent.inspect()))

    print("\nregister_module (child registration via attribute assignment):")
    target = Identity()
    counter = {"i": 0}

    def register():
        setattr(target, f"child{counter['i']}", Identity())
        counter["i"] += 1

    print(timeit(register, iterations=5_000))


if __name__ == "__main__":
    main()
