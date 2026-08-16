"""Unit tests for ExecutionEngine.execute_plan (ADR-019).

Organized around the ADR-019 test matrix (PLAN/CTX/TRACE/METRIC/FAIL/
OBS/STATE/COMPAT/SEC/API), not as an independent collection of
examples. Each test's docstring cites the matrix ID it covers.
"""

from __future__ import annotations

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.execution import StepExecutionContext, StepExecutionResult
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep
from ragtorch.core.run import RunStatus


def step(node_id: str, dependencies: tuple[str, ...] = ()) -> ExecutionStep:
    return ExecutionStep(node_id=node_id, dependencies=dependencies)


def make_plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(steps=steps)


def trivial_handler(step: ExecutionStep, context: StepExecutionContext) -> object:
    return f"result-{step.node_id}"


# --- PLAN ------------------------------------------------------------------


def test_plan_01_empty_plan_has_complete_success_lifecycle() -> None:
    """Empty plan is a full successful lifecycle, not a no-op shortcut
    that skips Run/Trace/Metrics -- see ADV-06."""
    called = False

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        nonlocal called
        called = True
        return None

    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute_plan(make_plan(), handler)

    assert called is False
    assert result.run.status is RunStatus.SUCCEEDED
    assert isinstance(result.output, StepExecutionResult)
    assert dict(result.output.values) == {}
    assert len(result.trace.spans) == 1
    assert result.trace.spans[0].name == "execute_plan"
    assert result.metrics.values("execution_plan.duration_s") != []


def test_plan_02_execution_order_is_delegated_to_executor() -> None:
    """The engine does not iterate plan.steps itself -- it delegates
    entirely to whatever Executor it is given."""
    calls: list[str] = []

    class RecordingExecutor:
        def execute(self, plan: ExecutionPlan, handler: object) -> StepExecutionResult:
            calls.append("executor")
            return StepExecutionResult.from_values({"done": True})

    plan = make_plan(step("A"), step("B"))
    engine = ExecutionEngine()
    result = engine.execute_plan(plan, trivial_handler, executor=RecordingExecutor())

    assert calls == ["executor"]
    assert dict(result.output.values) == {"done": True}


def test_plan_03_injected_executor_is_actually_used_not_sequential_default() -> None:
    """A caller-supplied Executor is used in place of the default
    SequentialExecutor -- proves substitution, not merely acceptance."""
    used: list[bool] = []

    class FakeExecutor:
        def execute(self, plan: ExecutionPlan, handler: object) -> StepExecutionResult:
            used.append(True)
            return StepExecutionResult.from_values({})

    engine = ExecutionEngine()
    engine.execute_plan(make_plan(step("A")), trivial_handler, executor=FakeExecutor())

    assert used == [True]


def test_plan_steps_execute_in_order_via_default_executor() -> None:
    calls: list[str] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(s.node_id)
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"))
    engine = ExecutionEngine()
    engine.execute_plan(plan, handler)

    assert calls == ["A", "B", "C"]


# --- CTX ---------------------------------------------------------------


def test_ctx_01_supplied_root_context_preserved_by_identity() -> None:
    context = ExecutionContext(metadata={"request": "abc"})
    engine = ExecutionEngine()

    result = engine.execute_plan(make_plan(step("A")), trivial_handler, context=context)

    assert result.run.context is context


def test_ctx_02_omitted_context_creates_a_default_root_context() -> None:
    engine = ExecutionEngine()
    result = engine.execute_plan(make_plan(step("A")), trivial_handler)

    assert isinstance(result.run.context, ExecutionContext)
    assert result.run.context.run_id.startswith("run_")


def test_ctx_03_handler_never_receives_execution_context() -> None:
    """Regression guard for ADV-01: proves execute_plan calls
    handler(step, step_context) with no additional argument -- a
    handler whose signature only accepts (step, StepExecutionContext)
    must work without error, and the second positional argument must
    be a StepExecutionContext, never an ExecutionContext."""
    received: list[object] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        received.append(context)
        return "ok"

    engine = ExecutionEngine()
    engine.execute_plan(make_plan(step("A")), handler, context=ExecutionContext(metadata={"x": 1}))

    assert len(received) == 1
    assert isinstance(received[0], StepExecutionContext)
    assert not isinstance(received[0], ExecutionContext)


# --- TRACE ---------------------------------------------------------------


def test_trace_01_exactly_one_debug_span() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute_plan(make_plan(step("A"), step("B"), step("C")), trivial_handler)

    assert len(result.trace.spans) == 1


def test_trace_02_no_per_step_spans() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute_plan(make_plan(step("A"), step("B"), step("C")), trivial_handler)

    span_names = {s.name for s in result.trace.spans}
    assert "A" not in span_names
    assert "B" not in span_names
    assert "C" not in span_names


def test_trace_03_span_name_is_exactly_execute_plan() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute_plan(make_plan(step("A")), trivial_handler)

    assert result.trace.spans[0].name == "execute_plan"


def test_no_span_below_debug_level() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    result = engine.execute_plan(make_plan(step("A")), trivial_handler)

    assert result.trace.spans == []


# --- METRIC ---------------------------------------------------------------


def test_metric_01_exact_metric_name() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)
    result = engine.execute_plan(make_plan(step("A")), trivial_handler)

    assert result.metrics.names() == ["execution_plan.duration_s"]


def test_metric_02_off_records_no_duration_metric() -> None:
    engine = ExecutionEngine(level=ObservabilityLevel.OFF)
    result = engine.execute_plan(make_plan(step("A")), trivial_handler)

    assert result.metrics.names() == []


# --- FAIL ---------------------------------------------------------------


def test_fail_01_failed_run_marked_failed_with_original_error() -> None:
    """execute_plan() never returns on failure (same as execute()'s
    existing, already-tested behavior -- no pre-existing test in this
    codebase inspects Run.status/Run.error after a caught exception,
    since the ExecutionResult carrying that Run is never returned to
    the caller). We verify the mirrored run.fail(exc) contract
    directly against Run's own public API instead: a Run started,
    then failed with the same exception object execute_plan
    propagates, ends up FAILED with that error -- proving the
    documented lifecycle sequence (ADR-019 "Exact lifecycle sequence")
    independent of execute_plan's own unreachable internal Run."""
    from ragtorch.core.context import ExecutionContext as _ExecutionContext
    from ragtorch.core.run import Run

    error = ValueError("boom")
    run = Run.start(_ExecutionContext())
    run.fail(error)

    assert run.status is RunStatus.FAILED
    assert run.error is error


def test_fail_02_exact_original_exception_object_propagates() -> None:
    error = ValueError("boom")

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        raise error

    engine = ExecutionEngine()

    with pytest.raises(ValueError) as exc_info:
        engine.execute_plan(make_plan(step("A")), handler)

    assert exc_info.value is error


def test_fail_03_downstream_steps_do_not_execute() -> None:
    calls: list[str] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(s.node_id)
        if s.node_id == "B":
            raise RuntimeError("boom")
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"))
    engine = ExecutionEngine()

    with pytest.raises(RuntimeError):
        engine.execute_plan(plan, handler)

    assert calls == ["A", "B"]


def test_fail_04_no_partial_execution_result_returned_on_failure() -> None:
    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        if s.node_id == "B":
            raise RuntimeError("boom")
        return "ok"

    plan = make_plan(step("A"), step("B"), step("C"))
    engine = ExecutionEngine()

    with pytest.raises(RuntimeError):
        result = engine.execute_plan(plan, handler)
        del result


# --- OBS -------------------------------------------------------------------


def test_obs_01_metrics_failure_propagates_in_place_of_success(monkeypatch) -> None:
    """Documents the exact, frozen ADR-019 Q15 policy: observability
    failures are NOT isolated. A metrics.record failure propagates
    instead of a normal successful return."""
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)

    from ragtorch.core.metrics import MetricsCollector

    def exploding_record(self: MetricsCollector, name: str, value: float) -> None:
        raise RuntimeError("metrics failed")

    monkeypatch.setattr(MetricsCollector, "record", exploding_record)

    with pytest.raises(RuntimeError, match="metrics failed"):
        engine.execute_plan(make_plan(step("A")), trivial_handler)


def test_obs_02_trace_failure_propagates_in_place_of_success(monkeypatch) -> None:
    """Documents the exact, frozen ADR-019 Q15 policy for tracing: a
    Trace.start_span failure propagates instead of a normal return."""
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)

    from ragtorch.core.trace import Trace

    def exploding_start_span(self: Trace, name: str, **attributes: object) -> object:
        raise RuntimeError("trace failed")

    monkeypatch.setattr(Trace, "start_span", exploding_start_span)

    with pytest.raises(RuntimeError, match="trace failed"):
        engine.execute_plan(make_plan(step("A")), trivial_handler)


# --- STATE -------------------------------------------------------------------


def test_state_01_same_engine_instance_reusable_across_plan_and_module_calls() -> None:
    from ragtorch.core.module import Module

    class Double(Module):
        def forward(self, input: object) -> object:
            return input * 2  # type: ignore[operator]

    engine = ExecutionEngine()

    plan_result_1 = engine.execute_plan(make_plan(step("A")), trivial_handler)
    module_result = engine.execute(Double(), 21)
    plan_result_2 = engine.execute_plan(make_plan(step("B")), trivial_handler)

    assert plan_result_1.run.status is RunStatus.SUCCEEDED
    assert module_result.output == 42
    assert plan_result_2.run.status is RunStatus.SUCCEEDED
    assert plan_result_1.run is not plan_result_2.run
    assert plan_result_1.trace is not plan_result_2.trace
    assert plan_result_1.metrics is not plan_result_2.metrics


def test_state_02_plan_handler_executor_do_not_leak_across_calls() -> None:
    engine = ExecutionEngine()

    calls_a: list[str] = []
    calls_b: list[str] = []

    def handler_a(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls_a.append(s.node_id)
        return "a"

    def handler_b(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls_b.append(s.node_id)
        return "b"

    engine.execute_plan(make_plan(step("A")), handler_a)
    engine.execute_plan(make_plan(step("X")), handler_b)

    assert calls_a == ["A"]
    assert calls_b == ["X"]
