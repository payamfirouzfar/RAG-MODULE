"""Performance baseline for Step 4's context propagation. Unlike Steps
1-3, no budget is asserted here — per the project's own guidance, we
measure first and freeze a budget in the evaluation report afterward,
rather than inventing a number before real data exists.

Run: python evaluation/step4_benchmark.py
"""

from __future__ import annotations

import time

from ragtorch.core.context import ExecutionContext
from ragtorch.core.engine import ExecutionEngine
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


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


class Identity(Module):
    def forward(self, input, *, context=None):
        return input


class OldStyleIdentity(Module):
    """No context parameter — exercises the signature-detection cache's
    False path, not just its True path."""

    def forward(self, input):
        return input


def main() -> None:
    ctx = ExecutionContext()

    print("ExecutionContext.child() (Step 2 primitive, re-measured as Step 4's building block):")
    print(timeit(lambda: ctx.child(step="x")))

    print("\nModule call with context=None (context-aware forward, unused):")
    aware = Identity()
    print(timeit(lambda: aware(1)))

    print(
        "\nModule call with a real context (context-aware forward, signature-detection True path):"
    )
    print(timeit(lambda: aware(1, context=ctx)))

    print("\nModule call with a real context, but forward() doesn't accept it")
    print("(signature-detection False path, context silently dropped):")
    old = OldStyleIdentity()
    print(timeit(lambda: old(1, context=ctx)))

    print("\nSequential, 1 step, no context (I1 baseline, should match Step 1 numbers):")
    seq1 = Sequential(Identity())
    print(timeit(lambda: seq1(1)))

    print("\nSequential, 1 step, with context (child() + propagation overhead):")
    print(timeit(lambda: seq1(1, context=ctx)))

    print("\nSequential, 10 steps, with context:")
    seq10 = Sequential(*[Identity() for _ in range(10)])
    print(timeit(lambda: seq10(1, context=ctx), iterations=5_000))

    print("\nNested Sequential (outer of 2, each containing 5 steps), with context:")
    nested = Sequential(
        Sequential(*[Identity() for _ in range(5)]),
        Sequential(*[Identity() for _ in range(5)]),
    )
    print(timeit(lambda: nested(1, context=ctx), iterations=5_000))

    print("\nExecutionEngine executing a nested pipeline end-to-end (BASIC level):")
    engine = ExecutionEngine()
    print(timeit(lambda: engine.execute(nested, 1)))


if __name__ == "__main__":
    main()
