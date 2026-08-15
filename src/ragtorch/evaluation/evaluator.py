"""Evaluator: runs a system and a set of metrics over a set of cases."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.metric import Metric
from ragtorch.evaluation.result import CaseResult, EvaluationResult, current_git_commit, now


class Evaluator:
    """Runs ``system`` over each case and scores the output with ``metrics``.

    ``system`` is any callable that maps a case's input to an output
    (e.g. a Module, a Sequential, or a plain function) — the evaluator
    does not depend on Module, so it can score non-ragtorch systems too.
    A metric raising, or the system itself raising, marks that case as
    an error rather than aborting the whole evaluation.
    """

    def __init__(self, metrics: Sequence[Metric], *, configuration_hash: str | None = None):
        self._metrics = list(metrics)
        self._configuration_hash = configuration_hash

    def evaluate(
        self,
        system: Callable[[Any], Any],
        cases: Sequence[EvaluationCase],
    ) -> EvaluationResult:
        started_at = now()
        case_results: list[CaseResult] = []
        for case in cases:
            case_results.append(self._evaluate_case(system, case))
        finished_at = now()
        return EvaluationResult(
            case_results=case_results,
            started_at=started_at,
            finished_at=finished_at,
            git_commit=current_git_commit(),
            configuration_hash=self._configuration_hash,
        )

    def _evaluate_case(self, system: Callable[[Any], Any], case: EvaluationCase) -> CaseResult:
        try:
            actual = system(case.input)
        except Exception as exc:  # isolate per-case failures deliberately
            return CaseResult(case_name=case.name, scores={}, error=str(exc))

        scores: dict[str, float] = {}
        for metric in self._metrics:
            try:
                scores[metric.name] = metric.score(case, actual)
            except Exception as exc:  # noqa: BLE001 - isolate per-metric failures deliberately
                return CaseResult(case_name=case.name, scores=scores, error=str(exc))
        return CaseResult(case_name=case.name, scores=scores)
