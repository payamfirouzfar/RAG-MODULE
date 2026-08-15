"""Metric: a generic, pluggable measurement over one evaluation case.

Metric is deliberately not LLM-shaped. ExactMatch and Latency below
need no model at all. An LLM-as-judge metric is just one more
implementation of this same interface — not a special case the
framework needs to know about.
"""

from __future__ import annotations

import time
from typing import Any, Protocol, runtime_checkable

from ragtorch.evaluation.case import EvaluationCase


@runtime_checkable
class Metric(Protocol):
    """A named measurement computed from a case's actual output.

    Implementations return a float score. What the score means (higher
    is better, 0/1 pass-fail, a raw latency in ms, ...) is up to the
    metric; EvaluationResult reports scores per-metric without judging.
    """

    name: str

    def score(self, case: EvaluationCase, actual: Any) -> float: ...


class ExactMatch:
    """1.0 if actual == case.expected, else 0.0."""

    name = "exact_match"

    def score(self, case: EvaluationCase, actual: Any) -> float:
        return 1.0 if actual == case.expected else 0.0


class Latency:
    """Wraps a callable's execution time as a metric, in milliseconds.

    Unlike ExactMatch, this metric needs to observe the call itself, so
    it exposes a context-manager style timer via `measure()` for the
    Evaluator to use, rather than scoring a precomputed `actual`.
    """

    name = "latency_ms"

    def __init__(self) -> None:
        self._elapsed_ms: float | None = None

    def measure(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        self._elapsed_ms = (time.perf_counter() - start) * 1000
        return result

    def score(self, case: EvaluationCase, actual: Any) -> float:
        if self._elapsed_ms is None:
            raise RuntimeError("Latency.measure() must be called before score().")
        return self._elapsed_ms
