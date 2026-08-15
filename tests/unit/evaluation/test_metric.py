from __future__ import annotations

import time

import pytest

from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.metric import ExactMatch, Latency, Metric


def test_exact_match_true():
    case = EvaluationCase(input="hi", expected="HI")
    assert ExactMatch().score(case, "HI") == 1.0


def test_exact_match_false():
    case = EvaluationCase(input="hi", expected="HI")
    assert ExactMatch().score(case, "hi") == 0.0


def test_exact_match_has_name():
    assert ExactMatch().name == "exact_match"


def test_exact_match_satisfies_metric_protocol():
    assert isinstance(ExactMatch(), Metric)


def test_latency_measure_records_elapsed_time():
    metric = Latency()

    def slow(x):
        time.sleep(0.01)
        return x

    case = EvaluationCase(input=1)
    result = metric.measure(slow, 1)
    assert result == 1
    score = metric.score(case, result)
    assert score >= 10  # at least 10ms


def test_latency_score_before_measure_raises():
    metric = Latency()
    case = EvaluationCase(input=1)
    with pytest.raises(RuntimeError):
        metric.score(case, None)
