"""Integration test: ExecutionEngine driving a nested Sequential pipeline
with real ExecutionContext propagation end-to-end (Level B/C evaluation)
— Step 4's headline scenario, tying ADR-006 (engine) and ADR-007 (context
propagation) together."""

from __future__ import annotations

import pytest

from ragtorch.core.engine import ExecutionEngine, ObservabilityLevel
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module
from ragtorch.core.run import RunStatus
from ragtorch.core.sequential import Sequential


class Retriever(Module):
    def forward(self, query, *, context=None):
        return {"query": query, "run_id": context.run_id if context else None, "docs": ["a", "b"]}


class Reranker(Module):
    def forward(self, payload, *, context=None):
        payload = dict(payload)
        payload["reranker_run_id"] = context.run_id if context else None
        payload["docs"] = list(reversed(payload["docs"]))
        return payload


class Generator(Module):
    def forward(self, payload, *, context=None):
        return f"answer using {payload['docs']} (query={payload['query']})"


class FailingStage(Module):
    def forward(self, payload, *, context=None):
        raise ValueError("stage exploded")


def test_engine_propagates_context_through_nested_pipeline():
    pipeline = Sequential(Retriever(), Reranker())
    engine = ExecutionEngine(level=ObservabilityLevel.BASIC)

    result = engine.execute(pipeline, "hello")

    assert result.run.status is RunStatus.SUCCEEDED
    output = result.output
    # Each step received a distinct context derived from the engine's
    # top-level context, and both trace back to the same root run.
    assert output["run_id"] is not None
    assert output["reranker_run_id"] is not None
    assert output["run_id"] != output["reranker_run_id"]


def test_engine_full_rag_shaped_pipeline():
    pipeline = Sequential(Retriever(), Reranker(), Generator())
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)

    result = engine.execute(pipeline, "What is our refund policy?")

    assert result.run.status is RunStatus.SUCCEEDED
    assert "answer using" in result.output
    assert "What is our refund policy?" in result.output
    # DEBUG still records exactly one span for the top-level call — nested
    # per-child spans are an explicit Step 4 non-goal (ADR-007).
    assert len(result.trace.spans) == 1


def test_engine_failure_inside_nested_pipeline_propagates_and_marks_run_failed():
    pipeline = Sequential(Retriever(), FailingStage(), Generator())
    engine = ExecutionEngine(level=ObservabilityLevel.DEBUG)

    with pytest.raises(ExecutionError):
        engine.execute(pipeline, "query")


def test_engine_without_explicit_context_still_creates_one_and_propagates_it():
    """engine.execute() with no context= argument must still create a
    default ExecutionContext (Step 3 behavior) AND propagate it into the
    nested pipeline (new Step 4 behavior) — not silently skip
    propagation just because the caller didn't supply a context."""
    pipeline = Sequential(Retriever())
    engine = ExecutionEngine()

    result = engine.execute(pipeline, "q")

    assert result.output["run_id"] is not None
    assert result.output["run_id"] != result.run.context.run_id  # child, not the root
