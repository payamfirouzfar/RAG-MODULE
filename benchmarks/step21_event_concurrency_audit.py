"""Step 21 benchmark: measure EventBus/EventScope cost under
single-threaded and concurrent conditions (no synchronization was
added -- see evaluation/step21-evaluation.md for why).

Run from the repository root with:
    python benchmarks/step21_event_concurrency_audit.py

Tiers:

A. single-threaded publish cost at 1/10/100/1,000 listeners
   (baseline, unchanged from Step 20 -- reconfirms no cost was added).
B. concurrent publish cost at 1/2/4/8 worker threads, fixed listener
   count, to observe whether GIL contention under concurrent publish
   is material.

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made. Not
wired into CI, matching the majority file-only precedent.
"""

from __future__ import annotations

import statistics
import sys
import threading
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

    print("Tier A -- single-threaded publish cost (baseline, unchanged since Step 20):")
    print()
    print(f"{'listeners':>10}  {'p50 (us)':>10}  {'p95 (us)':>10}")
    for count in (1, 10, 100, 1_000):
        bus = EventBus()
        for _ in range(count):
            bus.subscribe(lambda e: None)
        p50, p95 = measure(lambda bus=bus: bus.publish(event), samples=5_000)
        print(f"{count:>10}  {p50:>10.3f}  {p95:>10.3f}")

    print()
    print("Tier B -- concurrent publish cost (fixed 10 listeners, N worker threads):")
    print()
    print(f"{'workers':>10}  {'total publishes':>16}  {'wall time (s)':>14}  {'us/publish':>12}")

    publishes_per_worker = 5_000
    for worker_count in (1, 2, 4, 8):
        bus = EventBus()
        for _ in range(10):
            bus.subscribe(lambda e: None)

        barrier = threading.Barrier(worker_count)

        def worker(bus: EventBus = bus, barrier: threading.Barrier = barrier) -> None:
            barrier.wait(timeout=10)
            for _ in range(publishes_per_worker):
                bus.publish(event)

        threads = [threading.Thread(target=worker) for _ in range(worker_count)]
        start = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        total_time = time.perf_counter() - start
        total_publishes = publishes_per_worker * worker_count
        us_per_publish = (total_time / total_publishes) * 1_000_000

        row = f"{worker_count:>10}  {total_publishes:>16}  {total_time:>14.4f}"
        print(f"{row}  {us_per_publish:>12.4f}")

    print()
    print(f"python={sys.version.split()[0]}")
    print("Measurement only. No performance guarantee or threshold is established.")
    print("No synchronization primitive was added -- these numbers characterize")
    print("existing (Step 20) behavior under concurrency, not a new mechanism.")


if __name__ == "__main__":
    main()
