"""Step 10 benchmark: measure check_connection() overhead relative to
is_compatible() (ADR-014).

Run from the repository root with:
    python benchmarks/step10_composition_preconditions.py

Measures is_compatible() (Step 7 baseline) against check_connection()
for a compatible pair (should be roughly is_compatible() plus one
conditional) and an incompatible pair (should be somewhat more
expensive due to the f-string message construction on the raise path).

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5-9
benchmarks' methodology and the project's anti-flakiness policy.
Numbers are measured and reported as-is, not optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, check_connection, is_compatible


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float
    p99_us: float


def measure(fn, *, samples: int, warmup: int = 200) -> Result:
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

    valid_output = OutputPort(name="value", type=int)
    valid_input = InputPort(name="value", type=int)
    invalid_output = OutputPort(name="value", type=str)
    invalid_input = InputPort(name="value", type=int)

    def is_compatible_valid() -> None:
        is_compatible(valid_output, valid_input)

    def check_connection_valid() -> None:
        check_connection(valid_output, valid_input)

    def check_connection_invalid() -> None:
        try:
            check_connection(invalid_output, invalid_input)
        except ValidationError:
            pass

    results = {
        "is_compatible(valid)": measure(is_compatible_valid, samples=samples),
        "check_connection(valid)": measure(check_connection_valid, samples=samples),
        "check_connection(invalid, raises)": measure(check_connection_invalid, samples=samples),
    }

    print(f"samples={samples}")
    print()
    print("Step 10 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")

    print()
    valid_delta = results["check_connection(valid)"].p50_us - results["is_compatible(valid)"].p50_us
    print(
        "check_connection(valid) - is_compatible(valid) p50 delta: "
        f"{valid_delta:.3f}us (expected small: one extra conditional, no exception raised)"
    )
    invalid_delta = (
        results["check_connection(invalid, raises)"].p50_us
        - results["check_connection(valid)"].p50_us
    )
    print(
        "check_connection(invalid) - check_connection(valid) p50 delta: "
        f"{invalid_delta:.3f}us (expected larger: f-string construction + exception raise/catch)"
    )


if __name__ == "__main__":
    main()
