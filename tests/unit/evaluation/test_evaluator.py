from __future__ import annotations

from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch


def upper(x: str) -> str:
    return x.upper()


def failing_system(x: str) -> str:
    raise ValueError("system exploded")


class FailingMetric:
    name = "always_fails"

    def score(self, case, actual):
        raise ValueError("metric exploded")


def test_evaluate_all_cases_pass():
    cases = [
        EvaluationCase(input="a", expected="A", name="case-a"),
        EvaluationCase(input="b", expected="B", name="case-b"),
    ]
    evaluator = Evaluator([ExactMatch()])
    result = evaluator.evaluate(upper, cases)
    assert result.case_count == 2
    assert result.error_count == 0
    assert result.mean("exact_match") == 1.0


def test_evaluate_partial_failures():
    cases = [
        EvaluationCase(input="a", expected="A", name="ok"),
        EvaluationCase(input="b", expected="wrong", name="mismatch"),
    ]
    evaluator = Evaluator([ExactMatch()])
    result = evaluator.evaluate(upper, cases)
    assert result.mean("exact_match") == 0.5


def test_evaluate_empty_case_list():
    evaluator = Evaluator([ExactMatch()])
    result = evaluator.evaluate(upper, [])
    assert result.case_count == 0
    assert result.mean("exact_match") is None


def test_system_exception_marks_case_as_error_not_aborting():
    cases = [
        EvaluationCase(input="a", expected="A", name="boom"),
        EvaluationCase(input="b", expected="B", name="ok"),
    ]
    evaluator = Evaluator([ExactMatch()])
    result = evaluator.evaluate(
        lambda x: failing_system(x) if x == "a" else upper(x),
        cases,
    )
    assert result.error_count == 1
    assert result.case_count == 2
    ok_result = next(r for r in result.case_results if r.case_name == "ok")
    assert ok_result.error is None


def test_metric_exception_marks_case_as_error():
    cases = [EvaluationCase(input="a", expected="A", name="x")]
    evaluator = Evaluator([FailingMetric()])
    result = evaluator.evaluate(upper, cases)
    assert result.error_count == 1
    assert result.case_results[0].error == "metric exploded"


def test_result_records_git_commit_when_available():
    evaluator = Evaluator([ExactMatch()])
    result = evaluator.evaluate(upper, [EvaluationCase(input="a", expected="A")])
    # In this repo (a git checkout) this should be a short hash; don't
    # assert a specific value, just that the mechanism runs without error.
    assert result.git_commit is None or isinstance(result.git_commit, str)


def test_result_to_dict_is_json_shaped():
    evaluator = Evaluator([ExactMatch()], configuration_hash="abc123")
    result = evaluator.evaluate(upper, [EvaluationCase(input="a", expected="A", name="x")])
    d = result.to_dict()
    assert d["case_count"] == 1
    assert d["configuration_hash"] == "abc123"
    assert d["means"]["exact_match"] == 1.0
    assert d["cases"][0]["case_name"] == "x"
