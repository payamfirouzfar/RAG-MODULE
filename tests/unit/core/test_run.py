from __future__ import annotations

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError
from ragtorch.core.run import Run, RunStatus


def test_start_creates_running_run_with_default_context():
    run = Run.start()
    assert run.status is RunStatus.RUNNING
    assert run.started_at is not None
    assert isinstance(run.context, ExecutionContext)


def test_start_accepts_explicit_context():
    ctx = ExecutionContext()
    run = Run.start(ctx)
    assert run.context is ctx


def test_succeed_sets_status_output_and_finished_at():
    run = Run.start()
    run.succeed(output=42)
    assert run.status is RunStatus.SUCCEEDED
    assert run.output == 42
    assert run.finished_at is not None
    assert run.is_terminal


def test_fail_sets_status_and_error():
    run = Run.start()
    err = ValueError("boom")
    run.fail(err)
    assert run.status is RunStatus.FAILED
    assert run.error is err
    assert run.is_terminal


def test_cancel_sets_status():
    run = Run.start()
    run.cancel()
    assert run.status is RunStatus.CANCELLED
    assert run.is_terminal


def test_duration_none_while_running():
    run = Run.start()
    assert run.duration is None


def test_duration_is_nonnegative_after_finish():
    run = Run.start()
    run.succeed()
    assert run.duration is not None
    assert run.duration >= 0


def test_cannot_finish_twice():
    run = Run.start()
    run.succeed()
    with pytest.raises(ExecutionError):
        run.succeed()


def test_cannot_fail_a_pending_run_without_starting():
    run = Run(context=ExecutionContext())
    assert run.status is RunStatus.PENDING
    with pytest.raises(ExecutionError):
        run.succeed()


def test_cannot_cancel_terminal_run():
    run = Run.start()
    run.fail(ValueError("x"))
    with pytest.raises(ExecutionError):
        run.cancel()
