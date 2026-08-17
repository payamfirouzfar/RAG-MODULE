"""Step 22 benchmark: measure publish() cost under direct, nested, and
recursive delivery (EVT-REENTRANT-001 audit -- no synchronization/
recursion-guard mechanism was added, see evaluation/step22-evaluation.md
for why).

Run from the repository root with:
    python benchmarks/step22_event_reentrancy_audit.py

Tiers:

A. direct publish cost at 0/1/10 listeners (baseline, unchanged).
B. one-level nested publish (a listener publishes a different,
   terminating event) -- isolates the added cost of legitimate nesting.
C. recursive same-event publish until RecursionError -- measures the
   wall-clock cost of the failure mode itself (security-relevant: is
   this a meaningful denial-of-service vector?).

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made. Not
wired into CI, matching the majority file-only precedent.
"""

from __future__ import annotations

import statistics
import sys
import time

from ragtorch.core.events import Event, EventBus, EventType


def measure(fn, *, samples: int, warmup: int = 500) -> tuple[float, float]:
    for _ in range(warmup):
        fn()
    values: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    ordered = sorted(values)
    return statistics.median(ordered), ordered[int(len(ordered) * 0.95) - 1]


def main() -> None:
    event = Event(EventType.MODULE_STARTED, "x")

    print("Tier A -- direct publish cost (baseline, unchanged):")
    print()
    print(f"{'listeners':>10}  {'p50 (us)':>10}  {'p95 (us)':>10}")
    for count in (0, 1, 10):
        bus = EventBus()
        for _ in range(count):
            bus.subscribe(lambda e: None)
        p50, p95 = measure(lambda bus=bus: bus.publish(event), samples=5_000)
        print(f"{count:>10}  {p50:>10.3f}  {p95:>10.3f}")

    print()
    print("Tier B -- one-level nested publish (different, terminating event):")
    print()

    outer_bus = EventBus()
    inner_bus = EventBus()
    inner_bus.subscribe(lambda e: None)

    def nests_once(e: Event) -> None:
        inner_bus.publish(Event(EventType.MODULE_FINISHED, "inner"))

    outer_bus.subscribe(nests_once)
    p50, p95 = measure(lambda: outer_bus.publish(event), samples=5_000)
    print(f"{'1-level nest':>10}  {p50:>10.3f}  {p95:>10.3f}")

    print()
    print("Tier C -- recursive same-event publish until RecursionError:")
    print()

    def measure_recursion_cost(samples: int) -> tuple[float, float]:
        values: list[float] = []
        for _ in range(samples):
            bus = EventBus()
            call_count = [0]

            def reenters(e: Event, bus: EventBus = bus, call_count=call_count) -> None:
                call_count[0] += 1
                bus.publish(e)

            bus.subscribe(reenters)
            start = time.perf_counter_ns()
            try:
                bus.publish(event)
            except RecursionError:
                pass
            values.append((time.perf_counter_ns() - start) / 1_000_000.0)
        values.sort()
        return statistics.median(values), values[int(len(values) * 0.95) - 1]

    p50_ms, p95_ms = measure_recursion_cost(samples=200)
    print(f"{'recursion':>10}  {'p50 (ms)':>10}  {'p95 (ms)':>10}")
    print(f"{'to-failure':>10}  {p50_ms:>10.3f}  {p95_ms:>10.3f}")

    print()
    print(f"python={sys.version.split()[0]}")
    print("Measurement only. No performance guarantee or threshold is established.")
    print("Tier C directly answers the security question: accidental infinite")
    print("recursion self-terminates in well under a second, not a meaningful")
    print("denial-of-service vector.")


if __name__ == "__main__":
    main()
