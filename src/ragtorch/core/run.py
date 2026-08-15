"""Run: the record of one execution's lifecycle.

A Run is deliberately not a Module — Module describes WHAT performs
computation, Run describes ONE execution of that computation. Keeping
them separate means a single Module instance can be invoked many times
concurrently, each producing its own independent Run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError


class RunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Run:
    """Mutable record of one execution, from start to a terminal status.

    Construct with :meth:`start`, terminate with :meth:`succeed`,
    :meth:`fail`, or :meth:`cancel`. Each of those may only be called
    once and only while the run is still RUNNING.
    """

    context: ExecutionContext
    status: RunStatus = RunStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None
    output: Any = None
    error: BaseException | None = None

    @classmethod
    def start(cls, context: ExecutionContext | None = None) -> Run:
        run = cls(context=context or ExecutionContext())
        run.status = RunStatus.RUNNING
        run.started_at = time.monotonic()
        return run

    @property
    def duration(self) -> float | None:
        """Elapsed seconds, or None if the run hasn't finished yet."""
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def _finish(self, status: RunStatus) -> None:
        if self.status is not RunStatus.RUNNING:
            raise ExecutionError(
                f"Cannot transition Run from {self.status.value} to {status.value}; "
                f"only a RUNNING run can be terminated."
            )
        self.status = status
        self.finished_at = time.monotonic()

    def succeed(self, output: Any = None) -> Run:
        self._finish(RunStatus.SUCCEEDED)
        self.output = output
        return self

    def fail(self, error: BaseException) -> Run:
        self._finish(RunStatus.FAILED)
        self.error = error
        return self

    def cancel(self) -> Run:
        self._finish(RunStatus.CANCELLED)
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)
