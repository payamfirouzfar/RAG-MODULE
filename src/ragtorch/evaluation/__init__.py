"""Evaluation: first-class, model-agnostic quality/latency/cost measurement.

An LLM judge is one Metric implementation among many, not a special
case the framework needs to know about — see ADR-004.
"""

from ragtorch.evaluation.case import EvaluationCase
from ragtorch.evaluation.evaluator import Evaluator
from ragtorch.evaluation.metric import ExactMatch, Latency, Metric
from ragtorch.evaluation.result import CaseResult, EvaluationResult, current_git_commit

__all__ = [
    "EvaluationCase",
    "Metric",
    "ExactMatch",
    "Latency",
    "Evaluator",
    "CaseResult",
    "EvaluationResult",
    "current_git_commit",
]
