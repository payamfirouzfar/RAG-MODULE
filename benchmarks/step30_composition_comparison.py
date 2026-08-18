"""Step 30 benchmark: compare construction/execution overhead of plain
Python function composition vs. ragtorch.Sequential vs. ragtorch's
ExecutionEngine-wrapped execution, at varying pipeline lengths.

Purpose: answer an architectural question (does ragtorch's composition
machinery introduce meaningful overhead relative to plain Python, and
does that change with the number of modules?) -- not to establish a
threshold. Run from the repository root with:

    python benchmarks/step30_composition_comparison.py

No network. No provider. No GPU.
"""

from __future__ import annotations

import statistics
import time

from ragtorch import ExecutionEngine, Module, ObservabilityLevel, Sequential


class Identity(Module):
    def forward(self, x, *, context=None):
        return x + 1


def plain_pipeline(n: int):
    def run(x):
        for _ in range(n):
            x = x + 1
        return x

    return run


def _time_it(fn, iterations: int = 500) -> tuple[float, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1_000_000)  # microseconds
    return statistics.mean(samples), statistics.median(samples)


def _report(label: str, n: int, mean: float, median: float) -> None:
    print(f"{label + ', ' + str(n) + ' steps':45s} {mean:12.2f} {median:12.2f}")


def main() -> None:
    print("Step 30 composition overhead benchmark\n")
    print(f"{'shape':45s} {'mean (us)':>12s} {'median (us)':>12s}")

    for n in (1, 5, 20, 50):
        plain = plain_pipeline(n)
        mean, median = _time_it(lambda plain=plain: plain(0), iterations=1000)
        _report("plain python", n, mean, median)

        seq = Sequential(*[Identity() for _ in range(n)])
        mean, median = _time_it(lambda seq=seq: seq(0), iterations=1000)
        _report("Sequential (direct call)", n, mean, median)

        engine_off = ExecutionEngine(level=ObservabilityLevel.OFF)
        seq2 = Sequential(*[Identity() for _ in range(n)])
        mean, median = _time_it(
            lambda engine_off=engine_off, seq2=seq2: engine_off.execute(seq2, 0), iterations=1000
        )
        _report("ExecutionEngine OFF", n, mean, median)

        engine_debug = ExecutionEngine(level=ObservabilityLevel.DEBUG)
        seq3 = Sequential(*[Identity() for _ in range(n)])
        mean, median = _time_it(
            lambda engine_debug=engine_debug, seq3=seq3: engine_debug.execute(seq3, 0),
            iterations=1000,
        )
        _report("ExecutionEngine DEBUG (trace)", n, mean, median)
        print()

    print(
        "No threshold asserted -- this measures ragtorch's own composition/\n"
        "observability overhead at varying pipeline lengths to inform the\n"
        "Step 30 architecture audit, not to judge performance in isolation."
    )


if __name__ == "__main__":
    main()
