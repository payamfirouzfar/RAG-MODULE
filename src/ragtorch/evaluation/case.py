"""EvaluationCase: one input/expected-output pair to evaluate a system against."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    """One evaluation example.

    ``expected`` is optional: some metrics (e.g. latency, cost) don't
    need a ground-truth output at all, they just observe behavior.
    """

    input: Any
    expected: Any = None
    name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
