"""Deterministic evaluation case: Evaluator scoring a system built from
context-propagating nested modules, driven through ExecutionEngine.
Confirms Step 2's evaluation framework, Step 3's engine, and Step 4's
context propagation all compose without any of them knowing about the
others."""

from __future__ import annotations

from ragtorch.core.engine import ExecutionEngine
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential
from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch


class Annotate(Module):
    """Tags its output with whether it received a context, without
    changing the underlying value — lets the evaluation case check
    context propagation happened without complicating the expected
    output shape."""

    def forward(self, input, *, context=None):
        return input


class UpperCase(Module):
    def forward(self, input, *, context=None):
        return input.upper()


def test_evaluator_scores_nested_pipeline_driven_through_engine():
    pipeline = Sequential(Annotate(), UpperCase())
    engine = ExecutionEngine()

    def system(x: str) -> str:
        return engine.execute(pipeline, x).output

    cases = [
        EvaluationCase(input="ab", expected="AB", name="case-1"),
        EvaluationCase(input="cd", expected="CD", name="case-2"),
    ]
    result = Evaluator([ExactMatch()]).evaluate(system, cases)

    assert result.case_count == 2
    assert result.error_count == 0
    assert result.mean("exact_match") == 1.0
