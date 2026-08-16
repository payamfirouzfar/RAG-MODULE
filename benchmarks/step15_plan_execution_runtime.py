"""Step 15 benchmark: measure ExecutionEngine.execute_plan's runtime
overhead relative to a bare SequentialExecutor.execute call (ADR-019).

Run from the repository root with:
    python benchmarks/step15_plan_execution_runtime.py

This benchmark isolates runtime overhead (Run/Trace/MetricsCollector
creation, plus optional span/log bookkeeping) from ADR-018's
already-benchmarked O(n^2) StepExecutionContext snapshot-copying cost
(see benchmarks/step14_execution_boundary.py). Sizes are kept small
(10/100/1,000 steps) precisely because that O(n^2) term would dominate
and swamp the additive-overhead signal at larger sizes -- this
benchmark's question is "how much does the engine add on top of the
executor," not "how does the executor scale" (already answered).

Compares, for each plan size and each ObservabilityLevel (BASIC and
DEBUG):
    baseline: SequentialExecutor().execute(plan, handler)
    engine:   ExecutionEngine(level=level).execute_plan(plan, handler)

reporting total time, time-per-step, and the engine's additional
overhead (engine total - baseline total) for each combination.

As with every prior benchmark in this project: this measures, it does
not prove, an overhead bound. No threshold assertion is made; not
wired into CI as a blocking gate (matching Steps 13/14's precedent).
"""

from __future__ import annotations

import time

from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.execution import SequentialExecutor, StepExecutionContext
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep

SIZES = (10, 100, 1_000)
LEVELS = (ObservabilityLevel.BASIC, ObservabilityLevel.DEBUG)


def make_plan(size: int) -> ExecutionPlan:
    steps = tuple(ExecutionStep(node_id=f"n{i}", dependencies=()) for i in range(size))
    return ExecutionPlan(steps=steps)


def handler(step: ExecutionStep, context: StepExecutionContext) -> object:
    return step.node_id


def main() -> None:
    print("Step 15 measurements (ExecutionEngine.execute_plan overhead over SequentialExecutor):")
    print()
    header = (
        f"{'steps':>8}  {'level':>6}  {'baseline (s)':>13}  {'engine (s)':>11}  "
        f"{'overhead (s)':>13}  {'baseline us/step':>17}  {'engine us/step':>15}"
    )
    print(header)

    executor = SequentialExecutor()

    for size in SIZES:
        plan = make_plan(size)

        start = time.perf_counter()
        executor.execute(plan, handler)
        baseline_elapsed = time.perf_counter() - start

        for level in LEVELS:
            engine = ExecutionEngine(level=level)
            plan_for_engine = make_plan(size)

            start = time.perf_counter()
            engine.execute_plan(plan_for_engine, handler)
            engine_elapsed = time.perf_counter() - start

            overhead = engine_elapsed - baseline_elapsed
            baseline_us_per_step = (baseline_elapsed / size) * 1_000_000
            engine_us_per_step = (engine_elapsed / size) * 1_000_000

            print(
                f"{size:>8}  {level.value:>6}  {baseline_elapsed:>13.6f}  "
                f"{engine_elapsed:>11.6f}  {overhead:>13.6f}  "
                f"{baseline_us_per_step:>17.4f}  {engine_us_per_step:>15.4f}"
            )

    print()
    print("Overhead is expected to be roughly constant per call (Run/Trace/")
    print("MetricsCollector construction plus, at DEBUG, one span and two log")
    print("events) -- not growing with step count, unlike ADR-018's documented")
    print("context-copying cost, which this benchmark does not re-measure.")


if __name__ == "__main__":
    main()
