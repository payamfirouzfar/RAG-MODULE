"""Integration tests for the step execution boundary (ADR-018).

Exercises the public API surface end-to-end -- ExecutionPlan through
SequentialExecutor through a StepHandler back to a StepExecutionResult
-- without touching Component, CompositionGraph, or ExecutionEngine.
Complements tests/unit/core/test_execution.py, which covers the
mechanism in isolation; this file covers the externally visible
behavior a real caller would depend on.
"""

from __future__ import annotations

import pytest

from ragtorch import (
    ExecutionPlan,
    ExecutionStep,
    SequentialExecutor,
    StepExecutionContext,
)


def test_execution_boundary_runs_dependency_aware_handler() -> None:
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(node_id="retrieve", dependencies=()),
            ExecutionStep(node_id="rerank", dependencies=("retrieve",)),
            ExecutionStep(node_id="generate", dependencies=("rerank",)),
        )
    )

    def handler(step: ExecutionStep, context: StepExecutionContext) -> object:
        if step.node_id == "retrieve":
            return ["doc-a", "doc-b"]

        if step.node_id == "rerank":
            documents = context.results["retrieve"]
            assert documents == ["doc-a", "doc-b"]
            return ["doc-b"]

        if step.node_id == "generate":
            ranked = context.results["rerank"]
            assert ranked == ["doc-b"]
            return "answer"

        raise AssertionError(f"unexpected step: {step.node_id}")

    result = SequentialExecutor().execute(plan, handler)

    assert result.values["retrieve"] == ["doc-a", "doc-b"]
    assert result.values["rerank"] == ["doc-b"]
    assert result.values["generate"] == "answer"


def test_execution_boundary_stops_after_handler_failure() -> None:
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(node_id="first", dependencies=()),
            ExecutionStep(node_id="broken", dependencies=("first",)),
            ExecutionStep(node_id="never", dependencies=("broken",)),
        )
    )

    calls: list[str] = []

    def handler(step: ExecutionStep, context: StepExecutionContext) -> object:
        calls.append(step.node_id)

        if step.node_id == "broken":
            raise RuntimeError("handler failed")

        return step.node_id

    with pytest.raises(RuntimeError, match="handler failed"):
        SequentialExecutor().execute(plan, handler)

    assert calls == ["first", "broken"]
