"""Performance baseline for Step 2's execution/observability/evaluation
primitives, and — critically — the overhead observability adds on top of
plain Step 1 Module execution.

Run: python evaluation/step2_benchmark.py
"""

from __future__ import annotations

import time

from ragtorch.core.context import ExecutionContext
from ragtorch.core.metrics import MetricsCollector
from ragtorch.core.module import Module
from ragtorch.core.run import Run
from ragtorch.core.trace import Trace
from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch


class Identity(Module):
    def forward(self, input):
        return input


def timeit(fn, iterations: int = 20_000) -> dict[str, float]:
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1_000_000)  # microseconds
    samples.sort()
    n = len(samples)
    return {
        "p50": samples[int(n * 0.50)],
        "p95": samples[int(n * 0.95)],
        "p99": samples[int(n * 0.99)],
    }


def main() -> None:
    print("ExecutionContext creation:")
    print(timeit(lambda: ExecutionContext()))

    print("\nExecutionContext.child():")
    parent = ExecutionContext()
    print(timeit(lambda: parent.child(module="retriever")))

    print("\nRun.start() + succeed():")

    def run_lifecycle():
        r = Run.start()
        r.succeed(output=1)

    print(timeit(run_lifecycle))

    print("\nTrace: single span:")

    def single_span():
        trace = Trace()
        with trace.start_span("op"):
            pass

    print(timeit(single_span))

    print("\nTrace: 10 nested spans:")

    def nested_spans():
        trace = Trace()
        with trace.start_span("root"):
            for _ in range(10):
                with trace.start_span("child"):
                    pass

    print(timeit(nested_spans, iterations=5_000))

    print("\nMetricsCollector.record():")
    metrics = MetricsCollector()
    print(timeit(lambda: metrics.record("latency", 1.0)))

    print("\nModule call: plain (Step 1 baseline for comparison):")
    plain = Identity()
    print(timeit(lambda: plain(1)))

    print("\nModule call: wrapped with Run + Trace + Metrics (observability overhead):")
    observed_metrics = MetricsCollector()

    def observed_call():
        run = Run.start()
        trace = Trace()
        with trace.start_span("identity"):
            output = plain(1)
        run.succeed(output=output)
        observed_metrics.record("duration", run.duration or 0.0)

    print(timeit(observed_call))

    print("\nEvaluator: 100 cases, ExactMatch:")
    cases = [EvaluationCase(input=i, expected=i, name=f"case-{i}") for i in range(100)]
    evaluator = Evaluator([ExactMatch()])

    def evaluate_100():
        evaluator.evaluate(lambda x: x, cases)

    print(timeit(evaluate_100, iterations=200))

    print("\nEvaluator: 1000 cases, ExactMatch:")
    cases_1k = [EvaluationCase(input=i, expected=i, name=f"case-{i}") for i in range(1000)]

    def evaluate_1000():
        evaluator.evaluate(lambda x: x, cases_1k)

    print(timeit(evaluate_1000, iterations=30))


if __name__ == "__main__":
    main()
