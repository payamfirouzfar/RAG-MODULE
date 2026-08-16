"""Step 7 benchmark: measure Component ports overhead (ADR-011).

Run from the repository root with:
    python benchmarks/step7_component_ports.py

Measures, against the pre-existing Step 6 baseline (Module call
p50 ~1.9us, Sequential(10) p50 ~20.5us — recorded as fixed reference
data, not re-run here):

1. InputPort / OutputPort construction.
2. is_compatible() for compatible and incompatible port pairs.
3. Module(input) execution WITHOUT any port involved — the regression
   guard: a component author who never touches ports.py must pay
   literally zero cost, since nothing in the hot __call__ path
   references InputPort, OutputPort, or is_compatible.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5/6
benchmarks' methodology and the project's anti-flakiness policy.
Regression judgment is relative to the recorded baseline, not a fixed
absolute number. Numbers are measured and reported as-is, not
optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.module import Module
from ragtorch.core.ports import InputPort, OutputPort, is_compatible


class Identity(Module):
    def forward(self, input: int) -> int:
        return input


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
    samples = 50_000
    module = Identity()

    compatible_output = OutputPort(name="value", type=int)
    compatible_input = InputPort(name="value", type=int)
    incompatible_output = OutputPort(name="value", type=str)
    incompatible_input = InputPort(name="value", type=int)

    def construct_input_port() -> None:
        InputPort(name="documents", type=list)

    def construct_output_port() -> None:
        OutputPort(name="documents", type=list)

    def check_compatible() -> None:
        is_compatible(compatible_output, compatible_input)

    def check_incompatible() -> None:
        is_compatible(incompatible_output, incompatible_input)

    def call_module_without_ports() -> None:
        module(1)

    results = {
        "InputPort construction": measure(construct_input_port, samples=samples),
        "OutputPort construction": measure(construct_output_port, samples=samples),
        "is_compatible() - compatible pair": measure(check_compatible, samples=samples),
        "is_compatible() - incompatible pair": measure(check_incompatible, samples=samples),
        "Module(input) [no ports involved - regression guard]": measure(
            call_module_without_ports, samples=samples
        ),
    }

    print(f"samples={samples}")
    print()
    print("Baseline (Step 6, fixed reference, not re-measured here):")
    print("  Module call        p50 ~1.9us")
    print("  Sequential(10)     p50 ~20.5us")
    print()
    print("Step 7 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")


if __name__ == "__main__":
    main()
