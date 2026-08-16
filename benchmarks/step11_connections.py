"""Step 11 benchmark: measure Connection construction overhead relative
to check_connection() (ADR-015).

Run from the repository root with:
    python benchmarks/step11_connections.py

Measures Connection construction for a compatible pair against a
check_connection()-only baseline, an incompatible pair, equality, and
hash. Measured result: Connection(valid) costs several microseconds
more than check_connection() alone -- the frozen-dataclass __init__/
__post_init__ path (attribute assignment via object.__setattr__, four
isinstance/str checks, one nested check_connection() call) is not
free, even though each individual check is cheap. Recorded as-is, not
assumed from the individual checks' costs in isolation.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5-10
benchmarks' methodology and the project's anti-flakiness policy.
Numbers are measured and reported as-is, not optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, check_connection


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
    connection_a = Connection(
        source_node_id="a", source_port=valid_output, target_node_id="b", target_port=valid_input
    )
    connection_b = Connection(
        source_node_id="a", source_port=valid_output, target_node_id="b", target_port=valid_input
    )

    def check_connection_valid_baseline() -> None:
        check_connection(valid_output, valid_input)

    def connection_valid() -> None:
        Connection(
            source_node_id="a",
            source_port=valid_output,
            target_node_id="b",
            target_port=valid_input,
        )

    def connection_invalid() -> None:
        try:
            Connection(
                source_node_id="a",
                source_port=invalid_output,
                target_node_id="b",
                target_port=invalid_input,
            )
        except ValidationError:
            pass

    def connection_equality() -> None:
        connection_a == connection_b  # noqa: B015

    def connection_hash() -> None:
        hash(connection_a)

    results = {
        "check_connection(valid) [Step 10 baseline]": measure(
            check_connection_valid_baseline, samples=samples
        ),
        "Connection(valid)": measure(connection_valid, samples=samples),
        "Connection(invalid, raises)": measure(connection_invalid, samples=samples),
        "Connection.__eq__": measure(connection_equality, samples=samples),
        "hash(Connection)": measure(connection_hash, samples=samples),
    }

    print(f"samples={samples}")
    print()
    print("Step 11 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")

    print()
    overhead = (
        results["Connection(valid)"].p50_us
        - results["check_connection(valid) [Step 10 baseline]"].p50_us
    )
    print(
        "Connection(valid) - check_connection(valid) p50 delta: "
        f"{overhead:.3f}us (frozen-dataclass __init__/__post_init__ overhead: "
        "object.__setattr__ x4, four isinstance/str checks, one nested check_connection() call)"
    )


if __name__ == "__main__":
    main()
