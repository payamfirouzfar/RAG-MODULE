"""Metrics: numeric measurements recorded during execution.

Kept intentionally separate from Trace (timing/structure) and logging
(freeform events): a MetricsCollector records named numeric samples so
callers can later compute aggregates (p50/p95/p99, sums, counts) —
the same "measurable behavior" principle used for Step 1's performance
baselines, now available at runtime rather than only in benchmarks.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricSummary:
    count: int
    sum: float
    min: float
    max: float
    p50: float
    p95: float
    p99: float


class MetricsCollector:
    """Records named numeric samples and summarizes them on demand."""

    def __init__(self) -> None:
        self._samples: dict[str, list[float]] = defaultdict(list)

    def record(self, name: str, value: float) -> None:
        self._samples[name].append(value)

    def increment(self, name: str, amount: float = 1) -> None:
        self.record(name, amount)

    def values(self, name: str) -> list[float]:
        return list(self._samples.get(name, []))

    def names(self) -> list[str]:
        return list(self._samples.keys())

    def summarize(self, name: str) -> MetricSummary | None:
        samples = sorted(self._samples.get(name, []))
        if not samples:
            return None
        n = len(samples)
        return MetricSummary(
            count=n,
            sum=sum(samples),
            min=samples[0],
            max=samples[-1],
            p50=_percentile(samples, 0.50),
            p95=_percentile(samples, 0.95),
            p99=_percentile(samples, 0.99),
        )

    def summarize_all(self) -> dict[str, MetricSummary]:
        return {name: summary for name in self.names() if (summary := self.summarize(name))}


def _percentile(sorted_samples: list[float], fraction: float) -> float:
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    index = min(int(len(sorted_samples) * fraction), len(sorted_samples) - 1)
    return sorted_samples[index]
