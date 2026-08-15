"""Unit tests for Step 4: ExecutionContext propagation through Sequential.
See ADR-007."""

from __future__ import annotations

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class RecordContext(Module):
    """Records the context it was called with onto a shared list, so
    tests can inspect what each step actually received."""

    def __init__(self, sink: list):
        super().__init__()
        self.sink = sink

    def forward(self, input, *, context=None):
        self.sink.append(context)
        return input


class Boom(Module):
    def forward(self, input, *, context=None):
        raise ValueError("boom")


def test_sequential_without_context_runs_unchanged_i1():
    seq = Sequential()
    assert seq(42) == 42


def test_sequential_propagates_context_to_each_step():
    sink: list = []
    seq = Sequential(RecordContext(sink), RecordContext(sink))
    ctx = ExecutionContext()

    seq(1, context=ctx)

    assert len(sink) == 2
    assert all(c is not None for c in sink)


def test_sequential_gives_each_step_a_distinct_child_context_i4():
    sink: list = []
    seq = Sequential(RecordContext(sink), RecordContext(sink))
    ctx = ExecutionContext()

    seq(1, context=ctx)

    run_ids = {c.run_id for c in sink}
    assert len(run_ids) == 2  # each step got its own distinct context
    assert ctx.run_id not in run_ids  # neither step got the parent's raw context


def test_sequential_child_contexts_point_back_to_parent_i3():
    sink: list = []
    seq = Sequential(RecordContext(sink), RecordContext(sink))
    ctx = ExecutionContext()

    seq(1, context=ctx)

    assert all(c.parent_run_id == ctx.run_id for c in sink)


def test_sequential_with_no_context_gives_steps_none():
    sink: list = []
    seq = Sequential(RecordContext(sink), RecordContext(sink))

    seq(1)

    assert sink == [None, None]


def test_sibling_context_isolation():
    """One step's context/metadata must not be visible to or mutated by
    a sibling step — ExecutionContext is frozen, so this mainly confirms
    no shared mutable object is threaded between siblings."""
    sink: list = []
    seq = Sequential(RecordContext(sink), RecordContext(sink))
    ctx = ExecutionContext(metadata={"shared": "original"})

    seq(1, context=ctx)

    first, second = sink
    assert dict(first.metadata)["shared"] == "original"
    assert dict(second.metadata)["shared"] == "original"
    assert first is not second


def test_nested_sequential_propagates_context_through_multiple_levels():
    """outer = Sequential(inner, RecordContext) where inner is itself a
    Sequential(RecordContext, RecordContext). Verifies the context chain
    is: ctx -> outer's child (for inner) -> inner's child (for each of
    inner's two steps), i.e. depth is preserved through nesting, not
    flattened to a single level."""
    sink: list = []
    inner = Sequential(RecordContext(sink), RecordContext(sink))
    outer = Sequential(inner, RecordContext(sink))
    ctx = ExecutionContext()

    outer(1, context=ctx)

    assert len(sink) == 3
    inner_step_a, inner_step_b, outer_step1 = sink

    # outer's second step (a direct RecordContext) is one hop from ctx.
    assert outer_step1.parent_run_id == ctx.run_id

    # inner's two steps share a common parent: the context outer derived
    # for calling inner (outer's step0), which is itself one hop from ctx.
    assert inner_step_a.parent_run_id == inner_step_b.parent_run_id
    inner_parent_run_id = inner_step_a.parent_run_id
    assert inner_parent_run_id != ctx.run_id  # not flattened to depth 1


def test_failure_in_step_propagates_with_context_i5():
    seq = Sequential(Boom())
    ctx = ExecutionContext()
    with pytest.raises(ExecutionError):
        seq(1, context=ctx)


def test_failure_stops_subsequent_steps_from_executing():
    sink: list = []
    seq = Sequential(Boom(), RecordContext(sink))
    ctx = ExecutionContext()

    with pytest.raises(ExecutionError):
        seq(1, context=ctx)

    assert sink == []  # the step after Boom never ran
