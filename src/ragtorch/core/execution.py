"""Step execution boundary: runs an ExecutionPlan via a caller-supplied
handler (ADR-018).

SequentialExecutor answers "how does a plan actually get run?" -- it
walks plan.steps in order, invoking handler(step, context) for each,
and threads prior results forward through an immutable
StepExecutionContext snapshot rebuilt before every step. It never
resolves node_id -> Component itself; that is the handler's job,
supplied entirely by the caller. This keeps the executor provider-
independent by construction: it imports nothing from
ragtorch.core.component, ragtorch.core.composition, or
ragtorch.core.engine.

StepExecutionContext and StepExecutionResult are deliberately not
named ExecutionContext/ExecutionResult -- those names are already
taken by ragtorch.core.context.ExecutionContext (run identity/
metadata, ADR-002) and ragtorch.core.engine.ExecutionResult (Run/
Trace/MetricsCollector bundle, ADR-006), both unrelated types at
different layers. See ADR-018 "Naming" and "Post-merge finding".

Context construction copies the accumulated results dict before every
step (StepExecutionContext.from_results), which is O(n^2) total cost
across an n-step plan -- a known, accepted v0.1 trade-off in favor of
correct snapshot semantics (a later step must never observe a live
view that changes after its context was handed to it). See ADR-018
"Context construction cost" for why this is not silently optimized
away with unproven infrastructure.

Handler failures propagate unmodified -- no try/except here, no
ExecutionError wrapping. Unlike Module.__call__, this executor invokes
an opaque, caller-supplied handler rather than a fixed Component
contract, so there is no single "kind of event" to name; see ADR-018
Q11. A raising handler stops the plan immediately: no downstream step
runs, and no StepExecutionResult is ever constructed for a failed run
-- see ADR-018 "Partial-result policy".

Deliberately out of scope: ExecutionEngine integration, async/
parallel/distributed execution, retries, timeouts, a provider adapter,
and a persistent/optimized result-store data structure. See ADR-018
Non-goals.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep


@dataclass(frozen=True)
class StepExecutionContext:
    """Read-only snapshot of results from previously completed steps,
    keyed by node_id. Rebuilt fresh before each step -- a handler
    cannot mutate it back into the executor's own bookkeeping. The
    mapping itself is immutable; the objects stored as values are
    opaque, application-owned, and are not deep-copied or recursively
    frozen.
    """

    results: Mapping[str, object]

    @classmethod
    def from_results(cls, results: Mapping[str, object]) -> StepExecutionContext:
        return cls(results=MappingProxyType(dict(results)))


@dataclass(frozen=True)
class StepExecutionResult:
    """Every step's output from one execute() call, keyed by node_id.
    Only ever constructed after every step in the plan has completed
    successfully -- there is no partial-result contract. The mapping
    is immutable; stored values are opaque and not recursively frozen.
    """

    values: Mapping[str, object]

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> StepExecutionResult:
        return cls(values=MappingProxyType(dict(values)))


@runtime_checkable
class StepHandler(Protocol):
    """Caller-supplied: turns one ExecutionStep into work. The executor
    never inspects what a handler does -- it may call a Component, a
    plain function, or nothing at all.
    """

    def __call__(self, step: ExecutionStep, context: StepExecutionContext) -> object: ...


@runtime_checkable
class Executor(Protocol):
    """Run every step of an ExecutionPlan, in order, via handler.

    Synchronous only. An async executor cannot structurally satisfy
    this Protocol (async def execute(...) returns a Coroutine, not a
    StepExecutionResult) -- a future async use case is a separate,
    differently-named contract, not a variant of this one.
    """

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> StepExecutionResult: ...


class SequentialExecutor:
    """The only Executor implementation in this version: runs
    plan.steps in order, one at a time, threading prior results
    forward via StepExecutionContext.

    Behaviorally stateless: execution state from one execute() call
    never affects another, and the same instance is reusable across
    repeated, sequential calls. Thread-safety, reentrancy, and
    concurrent invocation of the same instance are separate, untested
    contracts not claimed here.

    Does not catch handler exceptions: a raising handler stops the
    plan immediately, and the original exception object propagates
    unmodified. Never returns a partial StepExecutionResult.
    """

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> StepExecutionResult:
        results: dict[str, object] = {}
        for step in plan.steps:
            context = StepExecutionContext.from_results(results)
            results[step.node_id] = handler(step, context)
        return StepExecutionResult.from_values(results)
