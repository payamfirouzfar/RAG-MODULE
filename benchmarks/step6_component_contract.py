"""Step 6 benchmark: measure Component contract overhead (ADR-010).

Run from the repository root with:
    python benchmarks/step6_component_contract.py

Measures, against the pre-existing Step 1-5 baseline (Module call
p50 ~1.9us, Sequential(10) p50 ~20.6us, inspect() p50 ~13.4us,
register_module p50 ~3.4us — recorded as fixed reference data, not
re-run here):

1. Module(input) execution — must not regress from adding name/
   component_type properties, since neither is on the hot __call__
   path.
2. module.name / module.component_type property access.
3. isinstance(module, Component) — measured separately and labeled
   informational, because ADR-010 explicitly prohibits this check
   from ever appearing on a hot execution path. This number exists
   so its real cost is documented, not assumed cheap.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5 benchmark's
methodology and the project's anti-flakiness policy. Regression
judgment is relative to the recorded baseline, not a fixed absolute
number.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.component import Component
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


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
    ten_step_sequential = Sequential(*[Identity() for _ in range(10)])

    def call_module() -> None:
        module(1)

    def call_sequential_10() -> None:
        ten_step_sequential(1)

    def access_name() -> None:
        module.name  # noqa: B018 - intentional attribute-access benchmark

    def access_component_type() -> None:
        module.component_type  # noqa: B018 - intentional attribute-access benchmark

    def check_isinstance_component() -> None:
        isinstance(module, Component)

    def call_inspect() -> None:
        module.inspect()

    results = {
        "Module(input)": measure(call_module, samples=samples),
        "Sequential(10)(input)": measure(call_sequential_10, samples=samples),
        "module.name": measure(access_name, samples=samples),
        "module.component_type": measure(access_component_type, samples=samples),
        "module.inspect()": measure(call_inspect, samples=samples),
        "isinstance(module, Component) [informational, not hot-path]": measure(
            check_isinstance_component, samples=samples
        ),
    }

    print(f"samples={samples}")
    print()
    print("Baseline (Steps 1-5, fixed reference, not re-measured here):")
    print("  Module call        p50 ~1.9us")
    print("  Sequential(10)     p50 ~20.6us")
    print("  inspect()          p50 ~13.4us")
    print("  register_module    p50 ~3.4us")
    print()
    print("Step 6 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")


if __name__ == "__main__":
    main()
