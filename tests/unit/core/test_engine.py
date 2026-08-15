from __future__ import annotations

import logging

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module
from ragtorch.core.run import RunStatus


class Double(Module):
    def forward(self, input):
        return input * 2


class Boom(Module):
    def forward(self, input):
        raise ValueError("kaboom")


def test_execute_success_returns_result_with_output():
    engine = ExecutionEngine()
    result = engine.execute(Double(), 21)
    assert result.output == 42
    assert result.run.status is RunStatus.SUCCEEDED


def test_execute_uses_given_context():
    engine = ExecutionEngine()
    ctx = ExecutionContext(metadata={"user": "abc"})
    result = engine.execute(Double(), 1, context=ctx)
    assert result.run.context is ctx


def test_execute_creates_default_context_when_none_given():
    engine = ExecutionEngine()
    result = engine.execute(Double(), 1)
    assert result.run.context is not None
    assert result.run.context.run_id.startswith("run_")


def test_execute_failure_reraises():
    # Module.__call__ wraps forward()'s exception in ExecutionError (Step 1
    # behavior); the engine must not swallow or alter that, only observe it.
    engine = ExecutionEngine()
    with pytest.raises(ExecutionError):
        engine.execute(Boom(), 1)


def test_execute_failure_preserves_original_exception_as_cause():
    engine = ExecutionEngine()
    with pytest.raises(ExecutionError) as exc_info:
        engine.execute(Boom(), 1)
    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "kaboom" in str(exc_info.value.__cause__)


def test_basic_level_records_duration_metric():
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    result = engine.execute(Double(), 5)
    assert result.metrics.values("Double.duration_s")


def test_basic_level_records_no_trace_spans():
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    result = engine.execute(Double(), 5)
    assert result.trace.spans == []


def test_off_level_records_no_metrics_and_no_trace():
    engine = ExecutionEngine(level=ObservabilityLevel.OFF)
    result = engine.execute(Double(), 5)
    assert result.metrics.names() == []
    assert result.trace.spans == []
    # Run tracking is not optional even at OFF.
    assert result.run.status is RunStatus.SUCCEEDED


def test_debug_level_records_trace_span():
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute(Double(), 5)
    spans = result.trace.spans
    assert len(spans) == 1
    assert spans[0].name == "Double"
    assert spans[0].status == "ok"


def test_debug_level_span_has_error_status_on_failure():
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    with pytest.raises(ExecutionError):
        engine.execute(Boom(), 1)


def test_debug_level_logs_start_and_finish(caplog):
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    with caplog.at_level(logging.INFO, logger="ragtorch.engine"):
        engine.execute(Double(), 5)
    messages = [r.message for r in caplog.records if r.name == "ragtorch.engine"]
    assert "run started" in messages
    assert "run finished" in messages


def test_debug_level_logs_failure(caplog):
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    with caplog.at_level(logging.INFO, logger="ragtorch.engine"):
        with pytest.raises(ExecutionError):
            engine.execute(Boom(), 1)
    messages = [r.message for r in caplog.records if r.name == "ragtorch.engine"]
    assert "run failed" in messages


def test_span_carries_run_id_attribute():
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    ctx = ExecutionContext()
    result = engine.execute(Double(), 5, context=ctx)
    assert result.trace.spans[0].attributes["run_id"] == ctx.run_id
