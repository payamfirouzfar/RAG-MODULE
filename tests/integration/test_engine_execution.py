"""Integration test: ExecutionEngine executing a Sequential graph
end-to-end, replacing the manual wiring the Step 2 integration test
had to hand-roll (see test_execution_lifecycle.py) with the guaranteed
engine contract (Level B/C evaluation)."""

from __future__ import annotations

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module
from ragtorch.core.run import RunStatus
from ragtorch.core.sequential import Sequential


class UpperCase(Module):
    def forward(self, input: str) -> str:
        return input.upper()


class Reverse(Module):
    def forward(self, input: str) -> str:
        return input[::-1]


class Explode(Module):
    def forward(self, input: str) -> str:
        raise ValueError("pipeline stage failed")


def test_engine_executes_sequential_pipeline_end_to_end():
    pipeline = Sequential(UpperCase(), Reverse())
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    context = ExecutionContext(metadata={"request": "r1"})

    result = engine.execute(pipeline, "hello", context=context)

    assert result.output == "OLLEH"
    assert result.run.status is RunStatus.SUCCEEDED
    assert result.run.context is context
    # DEBUG level records exactly one span for the top-level module call —
    # Sequential's own children aren't separately spanned by the engine
    # (that's out of scope per ADR-006; Sequential doesn't call back into
    # the engine for its steps).
    assert len(result.trace.spans) == 1
    assert result.trace.spans[0].name == "Sequential"
    assert result.metrics.values("Sequential.duration_s")


def test_engine_propagates_pipeline_failure():
    pipeline = Sequential(UpperCase(), Explode(), Reverse())
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)

    with pytest.raises(ExecutionError):
        engine.execute(pipeline, "hello")


def test_engine_at_off_level_still_produces_correct_output():
    pipeline = Sequential(UpperCase(), Reverse())
    engine = ExecutionEngine(level=ObservabilityLevel.OFF)

    result = engine.execute(pipeline, "abc")

    assert result.output == "CBA"
    assert result.run.status is RunStatus.SUCCEEDED
    assert result.trace.spans == []
    assert result.metrics.names() == []


def test_engine_reused_across_multiple_independent_executions():
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    pipeline = Sequential(UpperCase(), Reverse())

    result_a = engine.execute(pipeline, "ab")
    result_b = engine.execute(pipeline, "cd")

    assert result_a.output == "BA"
    assert result_b.output == "DC"
    # Each execute() call gets its own Run/Trace/Metrics — no shared state
    # leaking between independent executions of the same engine instance.
    assert result_a.run is not result_b.run
    assert result_a.run.context.run_id != result_b.run.context.run_id
