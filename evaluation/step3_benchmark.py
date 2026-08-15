"""Performance baseline for Step 3's ExecutionEngine, checked against the
budgets frozen in ADR-006:
  - BASIC level: < 50 us p50 overhead over a raw Module.__call__.
  - DEBUG level: < 25 us p50 additional overhead over BASIC.

Run: python evaluation/step3_benchmark.py
"""

from __future__ import annotations

import time

from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.module import Module

BASIC_BUDGET_US = 50.0
DEBUG_ADDITIONAL_BUDGET_US = 25.0


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
    module = Identity()

    print("Raw Module.__call__ (baseline):")
    raw = timeit(lambda: module(1))
    print(raw)

    print("\nExecutionEngine at OFF:")
    off_engine = ExecutionEngine(level=ObservabilityLevel.OFF)
    off = timeit(lambda: off_engine.execute(module, 1))
    print(off)

    print("\nExecutionEngine at BASIC (default):")
    basic_engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    basic = timeit(lambda: basic_engine.execute(module, 1))
    print(basic)

    print("\nExecutionEngine at DEBUG:")
    debug_engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    debug = timeit(lambda: debug_engine.execute(module, 1))
    print(debug)

    basic_overhead = basic["p50"] - raw["p50"]
    debug_additional_overhead = debug["p50"] - basic["p50"]

    print(
        f"\nBASIC overhead over raw call: {basic_overhead:.2f} us (budget: < {BASIC_BUDGET_US} us)"
    )
    print(
        f"DEBUG additional overhead over BASIC: {debug_additional_overhead:.2f} us "
        f"(budget: < {DEBUG_ADDITIONAL_BUDGET_US} us)"
    )

    basic_ok = basic_overhead < BASIC_BUDGET_US
    debug_ok = debug_additional_overhead < DEBUG_ADDITIONAL_BUDGET_US
    print(f"\nBASIC budget: {'PASS' if basic_ok else 'FAIL'}")
    print(f"DEBUG budget: {'PASS' if debug_ok else 'FAIL'}")


if __name__ == "__main__":
    main()
