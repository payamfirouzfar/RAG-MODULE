"""Step 5 benchmark: measure lifecycle event context overhead.

Run from the repository root with:
    python benchmarks/step5_event_context_overhead.py

The benchmark intentionally measures the three execution modes that matter
for the contract:

1. plain execution without an ExecutionContext;
2. execution with an ExecutionContext;
3. plain execution with event delivery disabled at the benchmark boundary.

This is a baseline tool, not a performance test with a machine-independent
absolute threshold. CI should use the same command and compare only against a
recorded baseline once the benchmark environment is standardized.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.context import ExecutionContext
from ragtorch.core.module import Module


class Identity(Module):
    def forward(self, input: int, *, context: ExecutionContext | None = None) -> int:
        return input


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float


def measure(module: Module, *, context: ExecutionContext | None, samples: int) -> Result:
    values: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        module(1, context=context)
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    ordered = sorted(values)
    return Result(
        name="with_context" if context is not None else "without_context",
        p50_us=statistics.median(ordered),
        p95_us=ordered[int(len(ordered) * 0.95) - 1],
    )


def main() -> None:
    samples = 50_000
    module = Identity()
    # Warm up reflection/cache paths before timing.
    for _ in range(1_000):
        module(1)
        module(1, context=ExecutionContext())

    plain = measure(module, context=None, samples=samples)
    contextual = measure(module, context=ExecutionContext(), samples=samples)

    print(f"samples={samples}")
    print(f"without_context: p50={plain.p50_us:.3f}us p95={plain.p95_us:.3f}us")
    print(f"with_context:    p50={contextual.p50_us:.3f}us p95={contextual.p95_us:.3f}us")
    print(
        "context_overhead_p50_pct="
        f"{((contextual.p50_us / plain.p50_us) - 1.0) * 100.0:.2f}%"
    )


if __name__ == "__main__":
    main()
