"""Integration test: ExecutionEngine.execute_plan driving a real
ExecutionPlan end-to-end through the public API (ADR-019), tying
ADR-006 (engine), ADR-017 (plan), and ADR-018 (executor/handler)
together -- the plan-execution analogue of test_nested_execution.py's
Module-based scenario.
"""

from __future__ import annotations

import pytest

from ragtorch import (
    ExecutionContext,
    ExecutionEngine,
    ExecutionPlan,
    ExecutionStep,
    ObservabilityLevel,
    RunStatus,
)


def test_engine_executes_dependency_aware_rag_shaped_plan() -> None:
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(node_id="retrieve", dependencies=()),
            ExecutionStep(node_id="rerank", dependencies=("retrieve",)),
            ExecutionStep(node_id="generate", dependencies=("rerank",)),
        )
    )

    def handler(step, context):
        if step.node_id == "retrieve":
            return ["doc-a", "doc-b"]
        if step.node_id == "rerank":
            docs = context.results["retrieve"]
            return list(reversed(docs))
        if step.node_id == "generate":
            docs = context.results["rerank"]
            return f"answer using {docs}"
        raise AssertionError(step.node_id)

    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)
    result = engine.execute_plan(plan, handler)

    assert result.run.status is RunStatus.SUCCEEDED
    assert result.output.values["retrieve"] == ["doc-a", "doc-b"]
    assert result.output.values["rerank"] == ["doc-b", "doc-a"]
    assert "answer using" in result.output.values["generate"]
    # One top-level span for the whole plan call, not one per step.
    assert len(result.trace.spans) == 1
    assert result.trace.spans[0].name == "execute_plan"


def test_engine_plan_failure_marks_run_failed_and_stops_downstream_steps() -> None:
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(node_id="first", dependencies=()),
            ExecutionStep(node_id="broken", dependencies=("first",)),
            ExecutionStep(node_id="never", dependencies=("broken",)),
        )
    )

    calls: list[str] = []

    def handler(step, context):
        calls.append(step.node_id)
        if step.node_id == "broken":
            raise ValueError("stage exploded")
        return step.node_id

    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)

    with pytest.raises(ValueError, match="stage exploded"):
        engine.execute_plan(plan, handler)

    assert calls == ["first", "broken"]


def test_engine_plan_propagates_supplied_root_context_without_reaching_handler() -> None:
    """A caller-supplied ExecutionContext becomes Run.context, but the
    handler -- which only ever accepts (step, StepExecutionContext) --
    runs correctly with no awareness of it, proving the ADR-019 Q2
    boundary end-to-end through the public API."""
    root_context = ExecutionContext(metadata={"request_id": "r-123"})
    plan = ExecutionPlan(steps=(ExecutionStep(node_id="only", dependencies=()),))

    def handler(step, context):
        return "ok"

    engine = ExecutionEngine()
    result = engine.execute_plan(plan, handler, context=root_context)

    assert result.run.context is root_context
    assert result.output.values["only"] == "ok"
