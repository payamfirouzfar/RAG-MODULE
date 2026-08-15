"""Integration test: ExecutionContext, Run, Trace, MetricsCollector, and
Evaluator working together over a Sequential pipeline (Level B/C
evaluation) — the framework's first complete execution lifecycle."""

from __future__ import annotations

from ragtorch.core.context import ExecutionContext
from ragtorch.core.metrics import MetricsCollector
from ragtorch.core.module import Module
from ragtorch.core.run import Run, RunStatus
from ragtorch.core.sequential import Sequential
from ragtorch.core.trace import Trace
from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch


class UpperCase(Module):
    def forward(self, input: str) -> str:
        return input.upper()


class Reverse(Module):
    def forward(self, input: str) -> str:
        return input[::-1]


def run_pipeline_with_observability(
    pipeline: Module, text: str, context: ExecutionContext, trace: Trace, metrics: MetricsCollector
) -> Run:
    run = Run.start(context)
    try:
        with trace.start_span("pipeline", input_len=len(text)):
            with trace.start_span("step0_upper"):
                intermediate = UpperCase()(text)
            with trace.start_span("step1_reverse"):
                output = Reverse()(intermediate)
        run.succeed(output=output)
    except Exception as exc:  # pragma: no cover - defensive, not exercised here
        run.fail(exc)
        raise
    finally:
        metrics.record("pipeline_duration_s", run.duration or 0.0)
    return run


def test_full_lifecycle_success_path():
    pipeline = Sequential(UpperCase(), Reverse())
    context = ExecutionContext(metadata={"user": "test"})
    trace = Trace()
    metrics = MetricsCollector()

    run = run_pipeline_with_observability(pipeline, "hello", context, trace, metrics)

    assert run.status is RunStatus.SUCCEEDED
    assert run.output == "OLLEH"
    assert run.context is context
    assert run.duration is not None and run.duration >= 0

    root_spans = trace.root_spans()
    assert len(root_spans) == 1
    assert root_spans[0].name == "pipeline"
    assert {c.name for c in trace.children_of(root_spans[0].span_id)} == {
        "step0_upper",
        "step1_reverse",
    }

    assert metrics.values("pipeline_duration_s")
    assert metrics.summarize("pipeline_duration_s") is not None


def test_full_lifecycle_evaluation_against_pipeline():
    pipeline = Sequential(UpperCase(), Reverse())
    cases = [
        EvaluationCase(input="ab", expected="BA", name="case-1"),
        EvaluationCase(input="hi", expected="IH", name="case-2"),
    ]
    evaluator = Evaluator([ExactMatch()])

    result = evaluator.evaluate(pipeline, cases)

    assert result.case_count == 2
    assert result.error_count == 0
    assert result.mean("exact_match") == 1.0


def test_nested_child_context_for_sub_execution():
    parent_ctx = ExecutionContext(metadata={"request": "r1"})
    child_ctx = parent_ctx.child(module="retriever")

    trace = Trace()
    with trace.start_span("retrieve", run_id=child_ctx.run_id):
        pass

    assert child_ctx.parent_run_id == parent_ctx.run_id
    assert trace.root_spans()[0].attributes["run_id"] == child_ctx.run_id
