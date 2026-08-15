"""Deterministic evaluation case exercising Evaluator against a system
driven through ExecutionEngine, not just a bare callable — confirms the
evaluation framework (Step 2) and the execution engine (Step 3) compose
without either needing to know about the other."""

from __future__ import annotations

from ragtorch.core.engine import ExecutionEngine
from ragtorch.core.module import Module
from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch


class UpperCase(Module):
    def forward(self, input: str) -> str:
        return input.upper()


def test_evaluator_can_score_a_system_run_through_the_engine():
    engine = ExecutionEngine()
    module = UpperCase()

    def system(x: str) -> str:
        return engine.execute(module, x).output

    cases = [
        EvaluationCase(input="ab", expected="AB", name="case-1"),
        EvaluationCase(input="cd", expected="CD", name="case-2"),
    ]
    result = Evaluator([ExactMatch()]).evaluate(system, cases)

    assert result.case_count == 2
    assert result.error_count == 0
    assert result.mean("exact_match") == 1.0
