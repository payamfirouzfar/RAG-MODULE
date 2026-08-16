"""Step 8 benchmark: measure architecture snapshot overhead (ADR-012).

Run from the repository root with:
    python benchmarks/step8_architecture_snapshot.py

Measures, against the pre-existing Step 1-7 baseline (Module call
p50 ~1.9-2.0us, Sequential(10) p50 ~20.5us, inspect() on an 11-module
tree p50 ~13.4us in Step 1's original benchmark — recorded as fixed
reference data, not re-run here):

1. snapshot() on a single (empty) module.
2. snapshot() on a 10-module tree.
3. snapshot() on a 100-module tree.
4. inspect() on a 10-module tree — now snapshot-backed (ADR-012
   migrated its implementation); this is the regression guard for
   that migration, since inspect()'s output must stay unchanged while
   its internals changed.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5/6/7
benchmarks' methodology and the project's anti-flakiness policy.
Regression judgment is relative to the recorded baseline, not a fixed
absolute number. Numbers are measured and reported as-is, not
optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.inspection import snapshot
from ragtorch.core.module import Module


class Leaf(Module):
    def forward(self, input: int) -> int:
        return input


class FlatContainer(Module):
    """A single-level container with N leaf children."""

    def __init__(self, count: int) -> None:
        super().__init__()
        for i in range(count):
            setattr(self, f"leaf{i}", Leaf())


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float
    p99_us: float


def measure(fn, *, samples: int, warmup: int = 1_000) -> Result:
    for _ in range(warmup):
        fn()

    values: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    ordered = sorted(values)
    n = len(ordered)
    return Result(
        name=fn.__name__ if hasattr(fn, "__name__") else "anonymous",
        p50_us=statistics.median(ordered),
        p95_us=ordered[int(n * 0.95) - 1],
        p99_us=ordered[int(n * 0.99) - 1],
    )


def main() -> None:
    samples = 20_000
    empty = Leaf()
    ten = FlatContainer(10)
    hundred = FlatContainer(100)

    def snapshot_empty() -> None:
        snapshot(empty)

    def snapshot_ten() -> None:
        snapshot(ten)

    def snapshot_hundred() -> None:
        snapshot(hundred)

    def inspect_ten() -> None:
        ten.inspect()

    results = {
        "snapshot() - empty module": measure(snapshot_empty, samples=samples),
        "snapshot() - 10-module tree": measure(snapshot_ten, samples=samples),
        "snapshot() - 100-module tree": measure(snapshot_hundred, samples=samples // 2),
        "inspect() - 10-module tree [snapshot-backed, regression guard]": measure(
            inspect_ten, samples=samples
        ),
    }

    print(f"samples={samples}")
    print()
    print("Baseline (Steps 1-7, fixed reference, not re-measured here):")
    print("  Module call            p50 ~1.9-2.0us")
    print("  Sequential(10)         p50 ~20.5us")
    print("  inspect() (11-module)  p50 ~13.4us (Step 1's original tree shape)")
    print()
    print("Step 8 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")


if __name__ == "__main__":
    main()
