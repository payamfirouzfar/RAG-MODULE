# ADR-018: Step Execution Boundary

## Status

Proposed

## Context

After Step 13, `ExecutionPlan` (ADR-017) can answer "given a valid
`CompositionGraph`, in what deterministic order should its nodes run,
and what does each node depend on?" — but nothing in the codebase yet
answers "how does a plan actually get run, and how does one planned
node's work actually happen?" `ExecutionStep.node_id` names a
`GraphNode.id`; `CompositionGraph` (ADR-016) is the only existing
structure mapping that id to a real `Component` instance; and
`ExecutionPlan` deliberately does not retain a reference to the graph
it was derived from (ADR-017). Something must walk `plan.steps` in
order, invoke whatever "work" each `node_id` represents, make prior
steps' results available to later ones, and surface failures — without
becoming a second `ExecutionEngine`, without knowing anything about
providers, and without prematurely deciding scheduling, concurrency,
retries, or observability.

`ExecutionEngine` (ADR-006/ADR-008) already exists and is bound to
`Module`, not `ExecutionPlan` — it coordinates
`Run`/`Trace`/`MetricsCollector` around a single `Module.__call__` and
re-raises failures after recording them (verified by reading
`engine.py`: `except Exception as exc: run.fail(exc); ...; raise`).
`Component` (ADR-010) remains deliberately minimal — `name`,
`component_type`, `__call__(input, *, context=None)` — with zero
provider or scheduling awareness. `docs/architecture/v0.1-architecture.md`
§2 already names "Runtime" as the layer that "executes an architecture
and owns execution identity, scheduling semantics, lifecycle, error
propagation, policies, and observability integration" — separate from
component business logic — so this ADR's boundary is not a new
invention, it is the first concrete piece of that already-named layer.

Grounded in direct inspection (14A audit) of `component.py`,
`context.py`, `engine.py`, `ports.py`, `composition.py`,
`execution_plan.py`, and `errors.py` — not assumed from memory.

**This ADR does not build `ExecutionEngine` integration, async
execution, parallel/distributed execution, retries, timeouts, or a
provider adapter.** It answers: given an `ExecutionPlan` and a
caller-supplied handler that knows how to turn one `node_id` into
work, what is the smallest stable, provider-independent contract for
running every step in order, threading prior results forward, and
propagating failure deterministically?

```text
CompositionGraph (ADR-016)
      |
      v
ExecutionPlan (ADR-017) -- WHAT order, WHAT depends on WHAT
      |
      v
Executor / SequentialExecutor (this ADR) -- runs the plan, step by step
      |
      v
StepHandler (caller-supplied) -- turns one node_id into work
      |
      v
Component / provider / model / retriever / etc. (caller's choice)

Future, independent of this ADR:
  AsyncExecutor, ParallelExecutor, DistributedExecutor -- alternate Executor implementations
  ExecutionEngine integration -- Run/Trace/Metrics, currently bound to Module
```

## Problem

We need a minimal, provider-independent contract for running an
`ExecutionPlan` to completion, where:

- the executor decides *only* iteration order and result bookkeeping —
  never what a node's work actually is;
- each step's work is performed by a caller-supplied `StepHandler`,
  identified only by `node_id`, so the executor never imports or
  references `Component`, `CompositionGraph`, or any provider;
- earlier steps' results are visible to later steps without allowing a
  handler to mutate the executor's own bookkeeping;
- failure in one step stops the plan deterministically rather than
  continuing to downstream steps or silently swallowing the error;
- the contract is written so alternate executors (async, parallel,
  distributed) can satisfy the same shape later without this version
  becoming a special case.

## Open questions this ADR must decide before any code is written

**Q1 — What does the executor consume?** An `ExecutionPlan` (ADR-017)
and a `StepHandler`. Not a `CompositionGraph` — `ExecutionPlan` already
carries the order and dependency information the executor needs, and
consuming the graph directly would mean recomputing what `plan()`
already computed, duplicating Step 13.

**Q2 — Does the executor resolve `node_id -> Component` itself?** No.
It never sees a `Component` at all. `node_id -> work` resolution is
entirely the handler's responsibility, supplied by the caller. Rejected:
an executor that accepts a `CompositionGraph` or a component registry
to resolve nodes itself — that would reopen `ExecutionPlan`'s explicit
non-retention-of-graph decision one layer up, and would hard-code
"work" to mean "a `Component` call," foreclosing the option of a
handler backed by something else (a test double, a non-`Component`
function) without any architectural benefit.

**Q3 — What does a handler receive?** `node_id: str` and an
`ExecutionContext` exposing prior steps' results
(`context.results: Mapping[str, object]`). Not the full
`ExecutionStep` (dependencies are already implicit in the plan's
ordering and in which prior results the handler chooses to read), and
not the `CompositionGraph` or `Component` — resolving `node_id` to
actual work is the handler's job, using whatever mapping the handler's
owner already has (typically `CompositionGraph.nodes`).

**Q4 — How do later steps see earlier steps' results?** Via
`ExecutionContext.results`, an immutable mapping rebuilt fresh before
each step and handed to that step's handler call — never the same
mutable dict the executor uses internally. Rejected: passing the raw
internal `dict` directly, which would let a handler mutate the
executor's own bookkeeping (`context.results["x"] = "bad"` silently
corrupting subsequent steps' view of history) — see Q9/ADV-05..08 for
the full immutability/statelessness reasoning.

**Q5 — What shape holds the final output?** `ExecutionResult`, a
frozen dataclass wrapping an immutable `values: Mapping[str, object]`
keyed by `node_id`, built once after every step completes — not
returned incrementally, not mutable after construction.

**Q6 — Does this ADR run more than one step?** Yes — unlike a
`StepExecutor`-shaped single-invocation boundary, this ADR's contract
*is* the plan runner: `Executor.execute(plan, handler) -> ExecutionResult`
walks every step in `plan.steps` in order and returns the aggregated
result. This intentionally supersedes an earlier single-step-only
draft of this ADR (see "Revision note" below).

**Q7 — Sync or async?** Synchronous in this version.
`SequentialExecutor` is one concrete implementation of the `Executor`
`Protocol`; a future `AsyncExecutor` or `ParallelExecutor` can satisfy
the same `Executor` contract shape (or a clearly-named async sibling
protocol) without this version becoming a special case. No
`async`/`Awaitable` is introduced now, since no consumer of this
boundary requires it yet.

**Q8 — Does the executor know about providers?** No. `Executor`,
`SequentialExecutor`, `StepHandler`, `ExecutionContext`, and
`ExecutionResult` mention no provider, model, or vendor SDK anywhere
in their contracts — the handler is the only place provider-specific
code can live, and it lives entirely outside this module, supplied by
the caller.

**Q9 — Does the executor retain the plan or context after execution?**
No. `SequentialExecutor.execute` is stateless: it holds no `self.plan`,
no `self._context`, no `self._results` surviving past the call. Each
call builds its own local `results: dict[str, object]`, discarded
(save for what's copied into the returned `ExecutionResult`) once
`execute` returns. This is a deliberate concurrency-readiness property:
a stateless executor can safely be reused or even shared across
concurrent `execute` calls in a future implementation without one
call's bookkeeping leaking into another's.

**Q10 — Failure behavior: swallow or propagate?** Propagate, and stop.
If a handler raises, `SequentialExecutor.execute` does not catch it,
does not continue to downstream steps, and does not return a partial
`ExecutionResult` — the exception propagates to the executor's caller
unmodified. This matches every existing execution-adjacent boundary in
this codebase (`Module.__call__`, `ExecutionEngine.execute`), which
re-raise/propagate rather than return a sentinel or a
`Result(success=False)` object.

**Q11 — Should failure information be wrapped?** No — propagated
as-is, unwrapped, via ordinary Python exception propagation (no
`try`/`except` in `SequentialExecutor.execute` at all). This is a
considered departure from `Module.__call__`'s `ExecutionError`-wrapping
convention, decided explicitly for this ADR's revision: the executor
here does not itself invoke a `Component` (see Q2/Q3) — it invokes a
caller-supplied `StepHandler` of unknown provenance, which may already
raise a meaningful, specific exception (including `ExecutionError`
itself, if the handler internally calls a `Component`/`Module`).
Wrapping an already-meaningful exception in a second layer of
`ExecutionError` here would obscure rather than clarify the failure,
and — because the handler is caller-owned, not a fixed `Component`
contract — there is no single "kind of event" this layer can name the
way `Module.__call__` names "a module raised." A handler that wants
`ExecutionError` semantics can raise one itself. See "Revision note"
below for why this differs from the previously-drafted `StepExecutor`
design, which *did* wrap, because it invoked `Component` directly.

**Q12 — Retry?** Not in this ADR. Deferred to a future policy layer,
for the same reasons given below in Non-goals.

**Q13 — Timeout?** Not in this ADR, for the same reason as Q12.

**Q14 — Concurrency?** Not implemented, but not foreclosed by the
`Executor` `Protocol`'s shape — see Q7/Q9.

**Q15 — Serialization?** Not implemented. `ExecutionResult` is a plain
frozen dataclass over a `Mapping`; nothing about this ADR requires it
to be serializable, and nothing prevents a caller from serializing
`result.values` themselves if its contents happen to be serializable.

**Q16 — Observability?** Not owned by `Executor`/`SequentialExecutor`
in this version. Connecting `ExecutionEngine`'s
`Run`/`Trace`/`Metrics` to plan-level execution is explicit, deferred
future work — see Non-goals.

**Q17 — Security / trust boundary?** Handler invocation is trusted
application code, exactly as `Module.__call__`/`ExecutionEngine.execute`
already treat component invocation. No new trust boundary, no
sandboxing.

**Q18 — API stability: what is the smallest contract confident enough
to freeze now?** `Executor` (`Protocol`, one method:
`execute(plan, handler) -> ExecutionResult`), `StepHandler`
(`Protocol`, one method: `__call__(node_id, context) -> object`),
`ExecutionContext` (frozen, `results: Mapping[str, object]`),
`ExecutionResult` (frozen, `values: Mapping[str, object]`), and
`SequentialExecutor` as the sole concrete `Executor` implementation.
No scheduler, retry policy, timeout policy, provider registry, or
distributed-execution concept is exposed.

## Revision note

An earlier draft of this ADR (commit `6f1ac10`, unmerged) defined a
narrower `StepExecutor.execute(step, component, input, *, context)`
that invoked exactly one already-resolved `Component` and wrapped
failures in `ExecutionError`, explicitly deferring any plan-wide
runner to a future step. That draft is **superseded** by this
revision at the project owner's explicit direction: Step 14 should
deliver the plan-runner boundary now (`Executor`/`SequentialExecutor`
walking `plan.steps`), with node-to-work resolution pushed into a
caller-supplied `StepHandler` rather than the executor accepting a
pre-resolved `Component`. This changes two decisions from the prior
draft: (1) the executor now runs a whole plan, not one step (Q6); (2)
failures propagate unwrapped rather than being wrapped in
`ExecutionError`, because the executor no longer invokes `Component`
directly and has no fixed "kind of event" to name (Q11).

## Decision

### Naming and location: `Executor`, `SequentialExecutor`, `src/ragtorch/core/execution.py`

A new module, not an addition to `execution_plan.py` (a different
concern: deriving an order vs. running one) or `engine.py` (a
different concern: `Module`-bound observability vs. plan-bound
iteration).

### Public contract

```python
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from ragtorch.core.execution_plan import ExecutionPlan


@dataclass(frozen=True)
class ExecutionContext:
    """Read-only view of results produced by steps already run in this
    execute() call, keyed by node_id. Rebuilt fresh before each step;
    a handler cannot mutate it back into the executor's bookkeeping."""

    results: Mapping[str, object]

    @classmethod
    def from_results(cls, results: Mapping[str, object]) -> "ExecutionContext":
        return cls(results=MappingProxyType(dict(results)))


@dataclass(frozen=True)
class ExecutionResult:
    """Every step's output from one execute() call, keyed by node_id."""

    values: Mapping[str, object]

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> "ExecutionResult":
        return cls(values=MappingProxyType(dict(values)))


@runtime_checkable
class StepHandler(Protocol):
    """Caller-supplied: turns one node_id into work. The executor never
    inspects what a handler does -- it may call a Component, a plain
    function, or nothing at all."""

    def __call__(self, node_id: str, context: ExecutionContext) -> object: ...


@runtime_checkable
class Executor(Protocol):
    """Run every step of an ExecutionPlan, in order, via handler."""

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> ExecutionResult: ...


class SequentialExecutor:
    """The only Executor implementation in this version: runs plan.steps
    in order, one at a time, threading prior results forward via
    ExecutionContext. Stateless -- retains no plan, context, or result
    state after execute() returns. Does not catch handler exceptions:
    a raising handler stops the plan immediately and propagates."""

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> ExecutionResult:
        results: dict[str, object] = {}
        for step in plan.steps:
            context = ExecutionContext.from_results(results)
            results[step.node_id] = handler(step.node_id, context)
        return ExecutionResult.from_values(results)
```

`Executor` and `StepHandler` are `Protocol`s, not concrete classes, so
a future async/parallel/distributed executor, or a test handler, can
satisfy the same contract without inheriting from `SequentialExecutor`
— matching the same structural-typing precedent `Component` (ADR-010)
already established for this codebase.

### Why the plan is not re-validated or re-derived

`ExecutionPlan.steps` (ADR-017) already encodes a valid, acyclic,
dependency-respecting order — `SequentialExecutor` trusts that
guarantee rather than re-checking it, the same single-source-of-truth
discipline every prior layer in this codebase has followed. It reads
only `step.node_id`; `step.dependencies` is not read by
`SequentialExecutor` itself in this version — a handler that wants a
step's declared dependencies can be given the full `ExecutionStep` by
its owner separately if needed, since the handler's owner (not the
executor) is the one wiring handlers to steps.

### Why failures are not wrapped here

See Q11 above.

### Why `ExecutionContext`/`ExecutionResult` are immutable and rebuilt, not shared

See Q4/Q9 above, and the adversarial tests in "Testing strategy" (ADV-05
through ADV-08), which specifically target plan/context/executor
statelessness and immutability as load-bearing properties for future
concurrency, not merely style preferences.

## Non-goals

Explicitly deferred, not part of this decision:

- **`ExecutionEngine` integration.** `execution.py` does not import
  `ragtorch.core.engine`.
- **Retries, timeouts, or any other invocation policy.** See Q12/Q13.
- **Concurrency, async, or distributed execution.** Not implemented;
  the `Executor`/`StepHandler` `Protocol` shapes do not foreclose
  either — see Q7/Q9/Q14.
- **A provider adapter or any `Component`-specific wiring.** The
  handler is entirely caller-supplied; this ADR does not define how a
  handler resolves `node_id -> Component`, nor does it import
  `ragtorch.core.component` or `ragtorch.core.composition`.
- **Serialization.** See Q15.
- **Observability beyond ordinary exception propagation.** See Q16.
- **A provider registry, sandboxing, or any new trust boundary.** See Q17.

## Alternatives considered

- **Have the executor accept an already-resolved `Component` per step
  (the previously-drafted `StepExecutor` design).** Superseded — see
  "Revision note." Rejected for this revision because it could only
  ever invoke one step, not run a plan, which is the capability this
  step is now scoped to deliver.
- **Wrap handler failures in `ExecutionError`, matching
  `Module.__call__`.** Rejected for this revision — see Q11. The
  executor no longer has a fixed "a `Component` raised" event to name,
  since the handler is caller-supplied and opaque.
- **Give the handler the raw internal `dict` instead of an immutable
  `ExecutionContext`.** Rejected: allows a handler to corrupt the
  executor's own bookkeeping, and forecloses safe reuse of the
  executor across concurrent calls in the future — see Q4/Q9.
- **Return results incrementally (e.g. a generator/iterator of
  per-step results) instead of one `ExecutionResult` at the end.**
  Rejected as a needless expansion of the contract's shape before any
  consumer has demonstrated a need for streaming results; `plan.steps`
  is already available to a caller that wants to observe the handler's
  own side effects step by step.
- **Make `Executor`/`StepHandler` concrete base classes, not
  `Protocol`s.** Rejected: `Component` (ADR-010) already establishes
  structural typing as this codebase's convention for "things that can
  be swapped without inheritance."

## Security

`SequentialExecutor.execute` performs no operation with external
effect itself — it only calls the caller-supplied `handler`, whose
behavior is entirely outside this module's control, exactly as
`Module.__call__` already treats component invocation as trusted
application code. No dynamic import, no `eval`/`exec`, no network
operation, no deserialization, no new credential handling. No
automatic logging of `context.results` or `result.values` — those may
contain sensitive data produced by handlers this module knows nothing
about.

## Dependency review

Zero new runtime dependencies. `execution.py` imports
`ragtorch.core.execution_plan` (`ExecutionPlan`), and the standard
library (`dataclasses`, `types.MappingProxyType`, `typing`) — no
`ragtorch.core.component`, no `ragtorch.core.composition`, no
`ragtorch.core.engine`, no provider SDK.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ArchitectureSnapshot`, `CompositionGraph`, `GraphNode`, `Connection`,
`ExecutionPlan`, `ExecutionStep`, or `plan()` themselves. `Executor`,
`StepHandler`, `ExecutionContext`, `ExecutionResult`, and
`SequentialExecutor` are a pure addition in a new module. Note:
`ExecutionContext` here is a distinct type from the identically-named
`ragtorch.core.context.ExecutionContext` (run identity/metadata,
ADR-002) — both are frozen dataclasses named `ExecutionContext` but
serve unrelated purposes at different layers; this name collision is
addressed explicitly in "Compatibility risk" below.

### Compatibility risk: `ExecutionContext` name collision

`ragtorch.core.context.ExecutionContext` (run_id, parent_run_id,
metadata) already exists and is exported publicly. This ADR introduces
a second, unrelated `ExecutionContext` (results mapping only) in
`ragtorch.core.execution`. Both are not exported under the same public
name simultaneously — `ragtorch.core.execution.ExecutionContext` is
**not** added to `ragtorch.core.__all__`/`ragtorch.__all__` under the
bare name `ExecutionContext`; callers that need both types import them
from their distinct modules explicitly
(`ragtorch.core.context.ExecutionContext` vs.
`ragtorch.core.execution.ExecutionContext`), and any public re-export
uses an unambiguous alias. The exact export decision is finalized
during implementation (14E) and recorded in the requirements matrix
evidence for A66, not left implicit.

## Testing strategy

- Unit: `SequentialExecutor.execute` on an empty plan
  (`ExecutionPlan(steps=())`) returns `ExecutionResult(values={})`
  without calling `handler`.
- Unit: single-step plan — handler is called once with that step's
  `node_id`, and `result.values` contains exactly that one entry.
- Unit: multi-step plan — handler is called once per step, in
  `plan.steps` order (verified via a recording fake handler).
- Unit: a later step's handler call receives a `context.results`
  containing every earlier step's already-computed value, keyed by
  `node_id`.
- Unit: `result.values` contains exactly one entry per step, keyed by
  `node_id`, with no duplicates and no missing steps.
- Immutability: `context.results[...] = ...` raises `TypeError` (or
  the `MappingProxyType` equivalent).
- Immutability: `result.values[...] = ...` raises `TypeError`.
- Failure: if `handler` raises for some step, the exception propagates
  unmodified out of `execute`, and no handler call happens for any
  step after the failing one (verified via a recording fake handler
  that would record a call it must never actually receive).
- Contract: `SequentialExecutor` satisfies the `Executor` `Protocol`
  (`isinstance(SequentialExecutor(), Executor)`).
- Contract: a plain function or lambda satisfying `StepHandler`'s call
  shape works identically to a class-based handler.
- **ADV-05 — plan is not mutated.** `plan == plan_before_execute` (and
  `plan.steps is plan.steps`, i.e. no in-place modification) after
  `execute` returns.
- **ADV-06 — executor retains no plan.** After `execute` returns, the
  `SequentialExecutor` instance holds no attribute referencing the
  plan (inspected via `vars(executor)` being empty, or equivalent).
- **ADV-07 — executor retains no context/results.** Same check for any
  `ExecutionContext`/results state.
- **ADV-08 — provider independence.** AST-based check: `execution.py`
  imports nothing from `ragtorch.core.component`,
  `ragtorch.core.composition`, `ragtorch.core.engine`, or any provider
  package.
- Regression: `CompositionGraph`, `ExecutionPlan`, `Sequential`,
  `ExecutionEngine`, `ragtorch.core.context.ExecutionContext`, and
  `Component` are all unmodified — the full pre-existing test suite
  passes unmodified.

## Benchmark strategy

Per ADR-009, `benchmarks/step14_execution_boundary.py`. Measures
`SequentialExecutor.execute` against a trivial handler
(`lambda node_id, context: node_id`) over plans of increasing step
count (10/100/1,000/10,000), reporting wall-clock time. This
establishes a baseline for future `AsyncExecutor`/`ParallelExecutor`
comparisons — it does not claim or prove an asymptotic complexity
bound, only reports measurements consistent (or not) with one,
following the same corrected methodology adopted for Step 13's
benchmark and evaluation report.

## Consequences

- Step 14 delivers a genuine plan-runner boundary: any caller with an
  `ExecutionPlan` and a way to turn a `node_id` into work can run the
  whole plan today, without waiting on `ExecutionEngine` integration
  or a provider adapter.
- Provider independence is structural: `execution.py` cannot import
  `Component`, `CompositionGraph`, or any provider, by construction —
  enforced by ADV-08, not merely by convention.
- The executor's statelessness and immutable
  `ExecutionContext`/`ExecutionResult` are deliberately chosen now so a
  future concurrent executor does not have to retrofit these
  properties under a compatibility constraint.
- Failure semantics are deliberately *not* unified with
  `Module.__call__`'s `ExecutionError` wrapping in this version — a
  considered trade-off (Q11), not an oversight; a handler that wants
  `ExecutionError` semantics raises one itself.
- Scope stays deliberately narrow: no `ExecutionEngine` integration, no
  retries, no timeouts, no concurrency, no provider adapter —
  consistent with every prior step's discipline.
