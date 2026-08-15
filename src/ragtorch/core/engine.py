"""ExecutionEngine: coordinates Run, Trace, and Metrics around one Module
call, so that guarantee doesn't depend on every caller re-deriving the
same wiring by hand. See ADR-006.

ExecutionEngine does not add new execution semantics — Module.__call__
still does the actual computation and its own event publishing. The
engine only guarantees that every execution produces a Run (and, at
higher observability levels, a Span and duration metric) without a
caller being able to accidentally skip a step.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ragtorch.core.context import ExecutionContext
from ragtorch.core.logging import get_logger, log_event
from ragtorch.core.metrics import MetricsCollector
from ragtorch.core.module import Module
from ragtorch.core.run import Run
from ragtorch.core.trace import Trace

_engine_logger = get_logger("engine")


class ObservabilityLevel(Enum):
    """How much the engine records for a given execution.

    FULL (retrieval candidates, token usage, cost, routing decisions) is
    deliberately not defined yet — those fields don't exist in the
    framework before retrieval/generation components do. Adding a level
    later is additive.
    """

    OFF = "off"
    BASIC = "basic"
    DEBUG = "debug"


@dataclass
class ExecutionResult:
    """Everything the engine produced for one execute() call."""

    run: Run
    trace: Trace
    metrics: MetricsCollector

    @property
    def output(self) -> Any:
        return self.run.output


class ExecutionEngine:
    """Executes a Module while guaranteeing the Step 2 observability
    contract: every call produces a Run; BASIC and above record a
    duration metric; DEBUG additionally records a trace span and
    start/finish log events.

    Failures are re-raised after being recorded — the engine never
    silently swallows an exception on the caller's behalf.
    """

    def __init__(self, level: ObservabilityLevel = ObservabilityLevel.BASIC) -> None:
        self.level = level

    def execute(
        self,
        module: Module,
        input: Any,
        context: ExecutionContext | None = None,
    ) -> ExecutionResult:
        context = context or ExecutionContext()
        run = Run.start(context)
        trace = Trace()
        metrics = MetricsCollector()
        module_name = type(module).__name__
        debug = self.level is ObservabilityLevel.DEBUG

        if debug:
            log_event(
                _engine_logger, logging.INFO, "run started", context=context, module=module_name
            )

        with self._maybe_span(trace, module_name, context, enabled=debug):
            try:
                output = module(input)
            except Exception as exc:
                run.fail(exc)
                self._record_duration(metrics, module_name, run)
                if debug:
                    log_event(
                        _engine_logger,
                        logging.ERROR,
                        "run failed",
                        context=context,
                        module=module_name,
                        error_type=type(exc).__name__,
                    )
                raise

        run.succeed(output)
        self._record_duration(metrics, module_name, run)
        if debug:
            log_event(
                _engine_logger,
                logging.INFO,
                "run finished",
                context=context,
                module=module_name,
                duration_s=run.duration,
            )

        return ExecutionResult(run=run, trace=trace, metrics=metrics)

    def _record_duration(self, metrics: MetricsCollector, module_name: str, run: Run) -> None:
        if self.level is not ObservabilityLevel.OFF:
            metrics.record(f"{module_name}.duration_s", run.duration or 0.0)

    @contextmanager
    def _maybe_span(
        self, trace: Trace, name: str, context: ExecutionContext, *, enabled: bool
    ) -> Iterator[None]:
        if not enabled:
            yield
            return
        with trace.start_span(name, run_id=context.run_id):
            yield
