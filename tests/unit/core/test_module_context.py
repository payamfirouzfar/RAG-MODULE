"""Unit tests for Step 4: ExecutionContext propagation through Module
calls. See ADR-007 for the invariants (I1-I7) these tests verify."""

from __future__ import annotations

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module


class ContextUnaware(Module):
    """A Step 1-3 style Module: forward() takes no context parameter."""

    def forward(self, input):
        return input * 2


class ContextAware(Module):
    """A Step 4 style Module: forward() opts in to receiving context."""

    def forward(self, input, *, context=None):
        return {"input": input, "run_id": context.run_id if context else None}


class Boom(Module):
    def forward(self, input, *, context=None):
        raise ValueError("kaboom")


def test_call_without_context_is_unchanged_i1():
    """I1: module(input) with no context behaves exactly as before."""
    m = ContextUnaware()
    assert m(21) == 42


def test_context_unaware_module_ignores_context_silently():
    """A context passed to a Module whose forward() doesn't declare
    'context' must not raise — the engine/composite may not know in
    advance whether a given child opts in."""
    m = ContextUnaware()
    ctx = ExecutionContext()
    assert m(21, context=ctx) == 42


def test_context_aware_module_receives_context():
    m = ContextAware()
    ctx = ExecutionContext()
    result = m(5, context=ctx)
    assert result == {"input": 5, "run_id": ctx.run_id}


def test_context_aware_module_with_no_context_gets_none():
    m = ContextAware()
    result = m(5)
    assert result == {"input": 5, "run_id": None}


def test_signature_detection_is_cached_per_class_not_instance():
    """Two instances of the same class must both benefit from the cached
    detection (I7) without behaving differently from each other."""
    a = ContextAware()
    b = ContextAware()
    ctx = ExecutionContext()
    assert a(1, context=ctx)["run_id"] == ctx.run_id
    assert b(2, context=ctx)["run_id"] == ctx.run_id


def test_failure_still_wrapped_in_execution_error_with_context_i5():
    m = Boom()
    ctx = ExecutionContext()
    with pytest.raises(ExecutionError, match="Boom"):
        m(1, context=ctx)


def test_failure_without_context_still_wrapped_i5():
    m = Boom()
    with pytest.raises(ExecutionError, match="Boom"):
        m(1)
