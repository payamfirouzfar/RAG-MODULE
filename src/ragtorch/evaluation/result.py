"""EvaluationResult: the machine-readable outcome of running an Evaluator.

Deliberately captures enough identity (git commit, config hash, when
available) to answer "which code and config produced this result?"
later, rather than only printing a number to the terminal.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CaseResult:
    case_name: str | None
    scores: dict[str, float]
    error: str | None = None


@dataclass(frozen=True)
class EvaluationResult:
    case_results: list[CaseResult]
    started_at: float
    finished_at: float
    git_commit: str | None = None
    configuration_hash: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at

    @property
    def case_count(self) -> int:
        return len(self.case_results)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.case_results if r.error is not None)

    def scores_for(self, metric_name: str) -> list[float]:
        return [
            r.scores[metric_name]
            for r in self.case_results
            if r.error is None and metric_name in r.scores
        ]

    def mean(self, metric_name: str) -> float | None:
        scores = self.scores_for(metric_name)
        if not scores:
            return None
        return sum(scores) / len(scores)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_count": self.case_count,
            "error_count": self.error_count,
            "duration": self.duration,
            "git_commit": self.git_commit,
            "configuration_hash": self.configuration_hash,
            "metadata": self.metadata,
            "means": {
                name: self.mean(name)
                for name in {name for r in self.case_results for name in r.scores}
            },
            "cases": [
                {"case_name": r.case_name, "scores": r.scores, "error": r.error}
                for r in self.case_results
            ],
        }


def current_git_commit() -> str | None:
    """Best-effort short git commit hash for the current working directory.

    Returns None (never raises) when not in a git repo or git isn't
    available — evaluation must still work without git.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def now() -> float:
    return time.time()
