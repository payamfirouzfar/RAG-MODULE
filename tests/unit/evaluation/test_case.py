from __future__ import annotations

import pytest

from ragtorch.evaluation.case import EvaluationCase


def test_case_defaults():
    case = EvaluationCase(input="hello")
    assert case.input == "hello"
    assert case.expected is None
    assert case.name is None
    assert dict(case.metadata) == {}


def test_case_with_expected_and_name():
    case = EvaluationCase(input="hi", expected="HI", name="uppercase-1")
    assert case.expected == "HI"
    assert case.name == "uppercase-1"


def test_case_metadata_is_immutable():
    source = {"difficulty": "easy"}
    case = EvaluationCase(input="x", metadata=source)
    source["difficulty"] = "hard"
    assert case.metadata["difficulty"] == "easy"
    with pytest.raises(TypeError):
        case.metadata["difficulty"] = "hard"  # type: ignore[index]
