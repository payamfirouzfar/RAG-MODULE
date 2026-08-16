"""Step 14 benchmark: measure SequentialExecutor.execute scaling
characteristics (ADR-018).

Run from the repository root with:
    python benchmarks/step14_execution_boundary.py

Measures SequentialExecutor.execute against a trivial handler over
plans of increasing step count (10 / 100 / 1,000 / 10,000 / 100,000),
reporting total wall-clock time and time-per-step for each size.

This benchmark exists specifically to make visible the accepted v0.1
cost documented in ADR-018 "Context construction cost":
StepExecutionContext.from_results copies the entire accumulated
results dict before every step, giving 0 + 1 + ... + (n-1) total copy
operations across an n-step plan -- quadratic, not linear, in step
count. A roughly constant time/step across sizes would be consistent
with linear behavior; a time/step that keeps growing with n is
consistent with the quadratic context-copying cost this benchmark is
built to expose.

As with every prior benchmark in this project: this measures, it does
not prove, an asymptotic bound. No threshold assertion is made here
that could make CI flaky -- numbers are measured and reported as-is.
The 100,000-step size is not part of the blocking CI gate (see
evaluation/step14-evaluation.md); CI runs a small smoke invocation
only, to verify the benchmark script still imports and executes
correctly.
"""

from __future__ import annotations

import time

from ragtorch.core.execution import SequentialExecutor, StepExecutionContext
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep

SIZES = (10, 100, 1_000, 10_000, 100_000)


def make_plan(size: int) -> ExecutionPlan:
    steps = tuple(ExecutionStep(node_id=f"n{i}", dependencies=()) for i in range(size))
    return ExecutionPlan(steps=steps)


def handler(step: ExecutionStep, context: StepExecutionContext) -> object:
    return step.node_id


def main() -> None:
    executor = SequentialExecutor()

    print("Step 14 measurements (SequentialExecutor.execute, trivial handler):")
    print()
    print(f"{'steps':>8}  {'total (s)':>12}  {'time/step (us)':>16}")

    results: list[tuple[int, float, float]] = []
    for size in SIZES:
        plan = make_plan(size)

        start = time.perf_counter()
        executor.execute(plan, handler)
        elapsed = time.perf_counter() - start

        time_per_step_us = (elapsed / size) * 1_000_000
        results.append((size, elapsed, time_per_step_us))
        print(f"{size:>8}  {elapsed:>12.6f}  {time_per_step_us:>16.4f}")

    print()
    print("Scaling check (time/step, expect roughly constant if linear;")
    print("growing time/step is consistent with the documented O(n^2)")
    print("context-copying cost -- see ADR-018 'Context construction cost'):")
    for size, _, time_per_step_us in results:
        print(f"  {size:>8} steps: {time_per_step_us:.4f}us/step")


if __name__ == "__main__":
    main()
