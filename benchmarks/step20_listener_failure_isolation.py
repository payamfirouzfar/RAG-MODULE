"""Step 20 benchmark: measure the cost of listener-failure isolation
(ADR-023).

Run from the repository root with:
    python benchmarks/step20_listener_failure_isolation.py

Two tiers, matching ADR-023's Benchmark strategy section:

1. no-failure baseline -- does the added try/except-per-listener and
   the listener-list snapshot cost anything measurable when nothing
   actually fails (the common case)?
2. failure-path cost -- with N listeners, how does isolate-and-continue
   compare to a plain loop with no try/except at all (not a literal
   "before ADR-023" comparison, since that code path no longer exists,
   but an isolation of the try/except overhead itself)?

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made. Not
wired into CI, matching the majority (12+ of 14) file-only precedent
this project established during Step 18's own 18H-1/18H-2 audit.
"""

from __future__ import annotations

import statistics
import sys
import time

from ragtorch.core.errors import ListenerDeliveryError
from ragtorch.core.events import Event, EventBus, EventType


def measure(fn, *, samples: int, warmup: int = 1_000) -> tuple[float, float]:
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
    samples = 20_000
    event = Event(EventType.MODULE_STARTED, "x")

    # Tier 1: no-failure baseline, at a few listener counts.
    print("Tier 1 -- no-failure baseline (isolate-and-continue's steady-state cost):")
    print()
    print(f"{'listeners':>10}  {'p50 (us)':>10}  {'p95 (us)':>10}")
    for count in (1, 10, 100):
        bus = EventBus()
        for _ in range(count):
            bus.subscribe(lambda e: None)
        p50, p95 = measure(lambda bus=bus: bus.publish(event), samples=samples)
        print(f"{count:>10}  {p50:>10.3f}  {p95:>10.3f}")

    print()
    print("Tier 2 -- failure-path cost (N listeners, all raise, isolate-and-continue):")
    print()
    print(f"{'listeners':>10}  {'p50 (us)':>10}  {'p95 (us)':>10}")

    def raises(e: Event) -> None:
        raise RuntimeError("boom")

    def publish_and_swallow(bus: EventBus) -> None:
        try:
            bus.publish(event)
        except ListenerDeliveryError:
            pass

    for count in (1, 10, 100):
        bus = EventBus()
        for _ in range(count):
            bus.subscribe(raises)
        p50, p95 = measure(lambda bus=bus: publish_and_swallow(bus), samples=samples)
        print(f"{count:>10}  {p50:>10.3f}  {p95:>10.3f}")

    print()
    print(f"python={sys.version.split()[0]}")
    print("Measurement only. No performance guarantee or threshold is established.")


if __name__ == "__main__":
    main()
