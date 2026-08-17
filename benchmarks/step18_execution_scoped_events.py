"""Step 18 benchmark: measure execution-scoped event delivery overhead
(ADR-022).

Run from the repository root with:
    python benchmarks/step18_execution_scoped_events.py

Three tiers, matching ADR-022's Benchmark strategy section exactly, to
separate "checking whether a scope is configured" overhead from
"actually delivering to a subscribed listener" overhead:

1. no scope        -- context=None, the exact pre-ADR-022 baseline
                       path (Module.__call__'s context-free branch;
                       NOT ExecutionContext() with event_scope=None,
                       which is a different, already-context-aware
                       code path -- see the corrected 18H record in
                       evaluation/step18-evaluation.md)
2. empty scope      -- event_scope=EventScope() with zero subscribers
3. active scope     -- event_scope=EventScope() with one subscriber

Tier 2 vs. tier 1 isolates the cost of the `context.event_scope is not
None` check and the extra no-op EventScope.publish() call. Tier 3 vs.
tier 2 isolates the cost of actual listener invocation.

As with every prior benchmark in this project (Steps 5, 13-17): this
measures, it does not prove, an overhead claim. No threshold assertion
is made. Per the 18H repository audit, only Step 5's benchmark is
actually wired into CI (as a non-blocking artifact upload) -- Steps
10-17's benchmarks, including this one, are not referenced in
.github/workflows/ci.yml at all. That is the majority precedent this
benchmark follows: a runnable, documented file, not a CI gate.
"""

from __future__ import annotations

import statistics
import sys
import time
from dataclasses import dataclass

from ragtorch.core.context import ExecutionContext
from ragtorch.core.events import EventScope
from ragtorch.core.module import Module


class Identity(Module):
    def forward(self, input: int, *, context: ExecutionContext | None = None) -> int:
        return input


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float


def measure(module: Module, *, context: ExecutionContext | None, samples: int, name: str) -> Result:
    values: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        module(1, context=context)
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    ordered = sorted(values)
    return Result(
        name=name,
        p50_us=statistics.median(ordered),
        p95_us=ordered[int(len(ordered) * 0.95) - 1],
    )


def main() -> None:
    samples = 50_000
    module = Identity()

    empty_scope_context = ExecutionContext(event_scope=EventScope())
    active_scope = EventScope()
    active_scope.subscribe(lambda event: None)
    active_scope_context = ExecutionContext(event_scope=active_scope)

    # Warm up reflection/cache paths (_forward_accepts_context's
    # per-class cache) before timing any tier. Tier 1 uses context=None
    # -- the real, unmodified pre-ADR-022 baseline path -- not
    # ExecutionContext(), which is a different, already-context-aware
    # code path inside Module.__call__.
    for _ in range(1_000):
        module(1, context=None)
        module(1, context=empty_scope_context)
        module(1, context=active_scope_context)

    no_scope = measure(module, context=None, samples=samples, name="no_scope")
    empty_scope = measure(module, context=empty_scope_context, samples=samples, name="empty_scope")
    active_scope_result = measure(
        module, context=active_scope_context, samples=samples, name="active_scope"
    )

    print(f"python={sys.version.split()[0]}")
    print(f"samples={samples}")
    print()
    print(f"{'tier':>14}  {'p50 (us)':>10}  {'p95 (us)':>10}")
    for result in (no_scope, empty_scope, active_scope_result):
        print(f"{result.name:>14}  {result.p50_us:>10.3f}  {result.p95_us:>10.3f}")
    print()

    check_overhead_pct = ((empty_scope.p50_us / no_scope.p50_us) - 1.0) * 100.0
    delivery_overhead_pct = ((active_scope_result.p50_us / empty_scope.p50_us) - 1.0) * 100.0
    total_overhead_pct = ((active_scope_result.p50_us / no_scope.p50_us) - 1.0) * 100.0

    print(f"scope_check_overhead_p50_pct={check_overhead_pct:.2f}%   (tier 2 vs. tier 1)")
    print(f"listener_delivery_overhead_p50_pct={delivery_overhead_pct:.2f}%   (tier 3 vs. tier 2)")
    print(f"total_scoped_overhead_p50_pct={total_overhead_pct:.2f}%   (tier 3 vs. tier 1)")
    print()
    print("Measurement only. No performance guarantee or threshold is established.")


if __name__ == "__main__":
    main()
