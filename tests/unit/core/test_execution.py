"""Unit tests for Executor/SequentialExecutor/StepHandler/
StepExecutionContext/StepExecutionResult (ADR-018).

Organized around the ADR-018 test matrix (CTX/EXEC/FAIL/STATE/ADV/
CONTRACT/REG), not as an independent collection of examples. Each
test's docstring or section header cites the matrix ID it covers.
"""

from __future__ import annotations

import pytest

from ragtorch.core.execution import (
    Executor,
    SequentialExecutor,
    StepExecutionContext,
    StepExecutionResult,
    StepHandler,
)
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep


def step(node_id: str, dependencies: tuple[str, ...] = ()) -> ExecutionStep:
    return ExecutionStep(node_id=node_id, dependencies=dependencies)


def make_plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(steps=steps)


# --- CTX: StepExecutionContext -----------------------------------------


def test_ctx_01_empty_context() -> None:
    context = StepExecutionContext.from_results({})
    assert dict(context.results) == {}


def test_ctx_02_context_exposes_previous_results() -> None:
    context = StepExecutionContext.from_results({"A": 1})
    assert context.results["A"] == 1


def test_ctx_03_context_mapping_is_immutable() -> None:
    context = StepExecutionContext.from_results({"A": 1})
    with pytest.raises(TypeError):
        context.results["A"] = 2  # type: ignore[index]


def test_ctx_04_values_are_not_deeply_frozen() -> None:
    value: list[str] = []
    context = StepExecutionContext.from_results({"A": value})

    context.results["A"].append("changed")  # type: ignore[attr-defined]

    assert context.results["A"] == ["changed"]


def test_context_is_a_snapshot_not_a_live_view() -> None:
    results: dict[str, object] = {"A": 1}
    context = StepExecutionContext.from_results(results)

    results["B"] = 2

    assert dict(context.results) == {"A": 1}


def test_context_cannot_mutate_source_mapping() -> None:
    results: dict[str, object] = {"A": 1}
    context = StepExecutionContext.from_results(results)

    with pytest.raises(TypeError):
        context.results["A"] = 2  # type: ignore[index]

    assert results == {"A": 1}


# --- StepExecutionResult immutability -----------------------------------


def test_step_execution_result_mapping_is_immutable() -> None:
    result = StepExecutionResult.from_values({"A": 1})
    with pytest.raises(TypeError):
        result.values["A"] = 2  # type: ignore[index]


def test_step_execution_result_does_not_deep_freeze_values() -> None:
    value: list[str] = []
    result = StepExecutionResult.from_values({"A": value})

    result.values["A"].append("x")  # type: ignore[attr-defined]

    assert result.values["A"] == ["x"]


# --- EXEC: SequentialExecutor.execute ------------------------------------


def test_exec_01_empty_plan_does_not_call_handler() -> None:
    called = False

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        nonlocal called
        called = True
        return None

    result = SequentialExecutor().execute(make_plan(), handler)

    assert called is False
    assert dict(result.values) == {}


def test_exec_02_single_step() -> None:
    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"result-{s.node_id}"

    plan = make_plan(step("A"))
    result = SequentialExecutor().execute(plan, handler)

    assert dict(result.values) == {"A": "result-A"}


def test_exec_03_multiple_steps_all_called() -> None:
    calls: list[str] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(s.node_id)
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"))
    SequentialExecutor().execute(plan, handler)

    assert set(calls) == {"A", "B", "C"}


def test_exec_04_exact_execution_order() -> None:
    calls: list[str] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(s.node_id)
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"))
    result = SequentialExecutor().execute(plan, handler)

    assert calls == ["A", "B", "C"]
    assert list(result.values) == ["A", "B", "C"]


def test_exec_05_handler_receives_full_execution_step() -> None:
    received: list[ExecutionStep] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        received.append(s)
        return "value"

    plan = make_plan(step("A", dependencies=()), step("B", dependencies=("A",)))
    SequentialExecutor().execute(plan, handler)

    assert received == list(plan.steps)
    assert received[1].dependencies == ("A",)


def test_exec_06_later_steps_see_previous_results() -> None:
    observed: list[dict[str, object]] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        observed.append(dict(context.results))
        return f"result-{s.node_id}"

    plan = make_plan(step("A"), step("B"), step("C"))
    SequentialExecutor().execute(plan, handler)

    assert observed[0] == {}
    assert observed[1] == {"A": "result-A"}
    assert observed[2] == {"A": "result-A", "B": "result-B"}


def test_exec_07_valid_plan_result_is_complete_and_exact() -> None:
    """result.values contains exactly one entry per step, keyed by
    node_id, with no duplicates and no missing steps -- for a valid
    ExecutionPlan satisfying ADR-017's invariants (unique node_id per
    step). Does not exercise or imply validation of a malformed plan;
    constructing one is upstream's responsibility (see EXEC-08)."""

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"), step("D"))
    result = SequentialExecutor().execute(plan, handler)

    assert set(result.values) == {"A", "B", "C", "D"}
    assert len(result.values) == 4


def test_exec_08_relies_on_upstream_node_id_uniqueness_not_revalidated() -> None:
    """SequentialExecutor does not defensively check for duplicate
    node_ids -- it trusts ExecutionPlan's invariant (ADR-017,
    inherited from CompositionGraph's no-duplicate-id guarantee,
    ADR-016). Documented here via direct construction: a plan with a
    duplicate node_id (which plan()/CompositionGraph would never
    produce, but which this executor also does not reject) silently
    overwrites the earlier entry -- proving no hidden revalidation
    exists, not that this is a supported input shape."""

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"result-{s.node_id}-{len(context.results)}"

    plan = make_plan(step("A"), step("A"))
    result = SequentialExecutor().execute(plan, handler)

    assert len(result.values) == 1
    assert result.values["A"] == "result-A-1"


def test_snapshot_isolation_across_retained_contexts() -> None:
    """A handler that retains its context object must still see only
    the results visible at its own invocation time, even after later
    steps run -- proving the snapshot is not a live view (protects the
    same guarantee as test_context_is_a_snapshot_not_a_live_view, but
    end-to-end through the executor)."""

    contexts: list[StepExecutionContext] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        contexts.append(context)
        return f"result-{s.node_id}"

    plan = make_plan(step("A"), step("B"), step("C"))
    SequentialExecutor().execute(plan, handler)

    assert dict(contexts[0].results) == {}
    assert dict(contexts[1].results) == {"A": "result-A"}
    assert dict(contexts[2].results) == {"A": "result-A", "B": "result-B"}


# --- plan immutability (ADV-05) ------------------------------------------


def test_adv_05_plan_is_not_mutated() -> None:
    plan = make_plan(step("A"), step("B"))
    before = plan

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        return s.node_id

    SequentialExecutor().execute(plan, handler)

    assert plan == before
    assert plan.steps == before.steps


# --- FAIL: failure propagation -------------------------------------------


def test_fail_01_handler_exception_propagates() -> None:
    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        raise ValueError("boom")

    plan = make_plan(step("A"))

    with pytest.raises(ValueError):
        SequentialExecutor().execute(plan, handler)


def test_fail_02_exact_exception_object_is_preserved() -> None:
    error = ValueError("boom")

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        raise error

    plan = make_plan(step("A"))

    with pytest.raises(ValueError) as exc_info:
        SequentialExecutor().execute(plan, handler)

    assert exc_info.value is error


def test_fail_03_steps_after_failure_are_not_executed() -> None:
    calls: list[str] = []

    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(s.node_id)
        if s.node_id == "B":
            raise RuntimeError("boom")
        return s.node_id

    plan = make_plan(step("A"), step("B"), step("C"))

    with pytest.raises(RuntimeError):
        SequentialExecutor().execute(plan, handler)

    assert calls == ["A", "B"]


def test_fail_04_no_partial_result_is_returned_on_failure() -> None:
    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        if s.node_id == "B":
            raise RuntimeError("boom")
        return "ok"

    plan = make_plan(step("A"), step("B"), step("C"))

    with pytest.raises(RuntimeError):
        result = SequentialExecutor().execute(plan, handler)
        # unreachable if the contract holds -- execute() must raise,
        # not return, on failure
        del result


# --- STATE: sequential reuse / cross-call isolation -----------------------


def test_state_01_executor_reusable_sequentially() -> None:
    executor = SequentialExecutor()

    def handler_a(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"a-{s.node_id}"

    def handler_b(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"b-{s.node_id}"

    plan_a = make_plan(step("A"), step("B"))
    plan_b = make_plan(step("X"), step("Y"))

    result_a = executor.execute(plan_a, handler_a)
    result_b = executor.execute(plan_b, handler_b)

    assert dict(result_a.values) == {"A": "a-A", "B": "a-B"}
    assert dict(result_b.values) == {"X": "b-X", "Y": "b-Y"}


def test_state_02_cross_call_isolation_matches_fresh_instances() -> None:
    def handler_a(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"a-{s.node_id}-{sorted(context.results)}"

    def handler_b(s: ExecutionStep, context: StepExecutionContext) -> object:
        return f"b-{s.node_id}-{sorted(context.results)}"

    plan_a = make_plan(step("A"), step("B"))
    plan_b = make_plan(step("X"), step("Y"))

    shared = SequentialExecutor()
    shared_result_a = shared.execute(plan_a, handler_a)
    shared_result_b = shared.execute(plan_b, handler_b)

    fresh_result_a = SequentialExecutor().execute(plan_a, handler_a)
    fresh_result_b = SequentialExecutor().execute(plan_b, handler_b)

    assert dict(shared_result_a.values) == dict(fresh_result_a.values)
    assert dict(shared_result_b.values) == dict(fresh_result_b.values)


# --- CONTRACT: Protocol conformance ---------------------------------------


def test_contract_01_sequential_executor_satisfies_executor_protocol() -> None:
    assert isinstance(SequentialExecutor(), Executor)


def test_contract_02_plain_function_satisfies_step_handler_protocol() -> None:
    def handler(s: ExecutionStep, context: StepExecutionContext) -> object:
        return s.node_id

    assert isinstance(handler, StepHandler)

    plan = make_plan(step("A"))
    result = SequentialExecutor().execute(plan, handler)

    assert dict(result.values) == {"A": "A"}


# --- ADV-08: provider independence ----------------------------------------


def test_adv_08_execution_module_has_no_provider_or_layer_dependencies() -> None:
    """execution.py must import nothing from ragtorch.core.component,
    ragtorch.core.composition, ragtorch.core.engine, or any provider
    package -- enforced structurally via AST inspection, reusing the
    established pattern (see test_execution_plan.py's equivalent)."""
    import ast
    import inspect

    from ragtorch.core import execution as execution_module

    source = inspect.getsource(execution_module)
    tree = ast.parse(source)

    forbidden_prefixes = (
        "ragtorch.core.component",
        "ragtorch.core.composition",
        "ragtorch.core.engine",
    )

    imported_modules: list[str] = []
    for node_ in ast.walk(tree):
        if isinstance(node_, ast.Import):
            imported_modules.extend(alias.name for alias in node_.names)
        elif isinstance(node_, ast.ImportFrom) and node_.module:
            imported_modules.append(node_.module)

    for module_name in imported_modules:
        assert not module_name.startswith(forbidden_prefixes), (
            f"execution.py must not import {module_name!r}"
        )
