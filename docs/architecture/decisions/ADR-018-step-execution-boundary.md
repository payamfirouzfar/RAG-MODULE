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
caller-supplied handler that knows how to turn one `ExecutionStep`
into work, what is the smallest stable, provider-independent contract
for running every step in order, threading prior results forward, and
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
StepHandler (caller-supplied) -- turns one ExecutionStep into work
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
  given the full `ExecutionStep` (not just `node_id`), so the executor
  never imports or references `Component`, `CompositionGraph`, or any
  provider;
- earlier steps' results are visible to later steps without allowing a
  handler to mutate the executor's own bookkeeping;
- failure in one step stops the plan deterministically rather than
  continuing to downstream steps or silently swallowing the error, and
  never produces a partial result;
- the contract is written so alternate executors (async, parallel,
  distributed) can satisfy an analogous shape later without this
  version becoming a special case, without overclaiming a
  `Protocol`-level compatibility Python's type system cannot actually
  provide for `async def`.

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

**Q3 — What does a handler receive?** The full `ExecutionStep` (not
only `node_id`) and a `StepExecutionContext` exposing prior steps'
results (`context.results: Mapping[str, object]`). **Revised during
14B adversarial review**: an earlier draft passed only `node_id`,
forcing a handler that needs `step.dependencies` (e.g. to gather only
its direct dependencies' results rather than every prior result) to
re-derive plan structure it has no direct access to — unnecessary
coupling to implicit plan semantics. Passing the full `ExecutionStep`
costs nothing (the executor already holds it while iterating
`plan.steps`) and lets a handler such as
`{d: context.results[d] for d in step.dependencies}` work without any
future contract change. The handler still does **not** receive the
`CompositionGraph` or `Component` — resolving a step to actual work is
the handler's job, using whatever mapping the handler's owner already
has (typically `CompositionGraph.nodes`).

**Q4 — How do later steps see earlier steps' results?** Via
`StepExecutionContext.results`, an immutable mapping snapshot rebuilt
before each step and handed to that step's handler call — never the
same mutable dict the executor uses internally, and never a live view
over it (see "Context construction cost" below for why a fresh
`MappingProxyType(dict(results))` snapshot, not a proxy over the live
dict, is required). Rejected: passing the raw internal `dict` directly,
or a `MappingProxyType` wrapping the *same* live dict across steps —
both let a handler observe (or, for the raw dict, mutate) state outside
the snapshot taken at its own invocation time — see Q9/ADV-05..08.

**Q5 — What shape holds the final output?** `ExecutionResult`, a
frozen dataclass wrapping an immutable `values: Mapping[str, object]`
keyed by `node_id`, built once after every step completes successfully
— never returned incrementally, never mutable after construction, and
**never returned partially**: see "Partial-result policy" below.

**Q6 — Does this ADR run more than one step?** Yes — unlike a
`StepExecutor`-shaped single-invocation boundary, this ADR's contract
*is* the plan runner: `Executor.execute(plan, handler) -> ExecutionResult`
walks every step in `plan.steps` in order and returns the aggregated
result. This intentionally supersedes an earlier single-step-only
draft of this ADR (see "Revision note" below).

**Q7 — Sync or async?** Synchronous only. **Revised during 14B
adversarial review**: an earlier draft claimed a future
`AsyncExecutor` "can satisfy the same `Executor` `Protocol`." That
claim is false and is retracted — `async def execute(...)` returns a
`Coroutine[..., ExecutionResult]`, not an `ExecutionResult`, so an
async implementation cannot structurally satisfy `Executor` as defined
here; Python's type system does not unify sync and async callables
under one `Protocol`. `Executor` in this ADR is therefore explicitly
the **synchronous** execution contract only. A future async use case
gets its own, separately-named protocol (e.g. `AsyncExecutor` with
`async def execute(...) -> ExecutionResult`) — a distinct contract,
not a variant satisfying this one. No `async`/`Awaitable` is
introduced now, since no consumer of this boundary requires it yet.

**Q8 — Does the executor know about providers?** No. `Executor`,
`SequentialExecutor`, `StepHandler`, `StepExecutionContext`, and
`ExecutionResult` mention no provider, model, or vendor SDK anywhere
in their contracts — the handler is the only place provider-specific
code can live, and it lives entirely outside this module, supplied by
the caller.

**Q9 — Does the executor retain the plan or context after execution?**
No — but this is now specified as a **behavioral** contract, not an
implementation-detail one. **Revised during 14B adversarial review**:
an earlier draft proposed testing statelessness via `vars(executor) ==
{}`, which tests an implementation detail (a future implementation
might legitimately hold e.g. `self._metrics` without retaining
execution state) rather than the actual invariant. The real invariant:
**execution state from one `execute()` call must never affect another**
— `executor.execute(plan_a, handler_a)` followed sequentially by
`executor.execute(plan_b, handler_b)` on the same `SequentialExecutor`
instance must behave identically to two separate instances, and the
same executor instance is reusable for repeated, sequential calls with
different plans/handlers without cross-contamination. This is verified
behaviorally (see Testing strategy, STATE-01/STATE-02), not by
inspecting `__dict__`. This is a **sequential-reuse** guarantee only —
thread-safety, reentrancy, and concurrent invocation of the same
instance are separate, untested contracts this ADR does not claim; see
Q14.

**Q10 — Failure behavior: swallow or propagate?** Propagate, and stop.
If a handler raises, `SequentialExecutor.execute` does not catch it,
does not continue to downstream steps, and does not return a partial
`ExecutionResult` — the exception propagates to the executor's caller
unmodified. This matches every existing execution-adjacent boundary in
this codebase (`Module.__call__`, `ExecutionEngine.execute`), which
re-raise/propagate rather than return a sentinel or a
`Result(success=False)` object. See "Partial-result policy" below for
why this is stated as an explicit, permanent contract rather than
current behavior that could quietly change.

**Q11 — Should failure information be wrapped?** No — propagated
as-is, unwrapped, via ordinary Python exception propagation (no
`try`/`except` in `SequentialExecutor.execute` at all), and the
**exact original exception object** is what propagates (not a copy,
not a re-raised instance of the same type) — see Testing strategy
FAIL-02. This is a considered departure from `Module.__call__`'s
`ExecutionError`-wrapping convention, decided explicitly for this
ADR's revision: the executor here does not itself invoke a `Component`
(see Q2/Q3) — it invokes a caller-supplied `StepHandler` of unknown
provenance, which may already raise a meaningful, specific exception
(including `ExecutionError` itself, if the handler internally calls a
`Component`/`Module`). Wrapping an already-meaningful exception in a
second layer of `ExecutionError` here would obscure rather than
clarify the failure, and — because the handler is caller-owned, not a
fixed `Component` contract — there is no single "kind of event" this
layer can name the way `Module.__call__` names "a module raised." A
handler that wants `ExecutionError` semantics can raise one itself.
See "Revision note" below for why this differs from the
previously-drafted `StepExecutor` design, which *did* wrap, because it
invoked `Component` directly.

**Q12 — Retry?** Not in this ADR. Deferred to a future policy layer,
for the same reasons given below in Non-goals.

**Q13 — Timeout?** Not in this ADR, for the same reason as Q12.

**Q14 — Concurrency?** Not implemented. `SequentialExecutor`'s
behavioral statelessness (Q9) is a deliberate precondition for a future
concurrent executor, but `Executor` as defined here is a strictly
synchronous, single-threaded contract (see Q7) — concurrency is future,
separate work, not something this `Protocol` shape already supports.

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
`execute(plan, handler) -> ExecutionResult`, synchronous only — see
Q7), `StepHandler` (`Protocol`, one method: `__call__(step, context) ->
object`), `StepExecutionContext` (frozen, `results: Mapping[str,
object]`), `ExecutionResult` (frozen, `values: Mapping[str, object]`),
and `SequentialExecutor` as the sole concrete `Executor`
implementation. No scheduler, retry policy, timeout policy, provider
registry, or distributed-execution concept is exposed.

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
pre-resolved `Component`. This changes two decisions from that prior
draft: (1) the executor now runs a whole plan, not one step (Q6); (2)
failures propagate unwrapped rather than being wrapped in
`ExecutionError`, because the executor no longer invokes `Component`
directly and has no fixed "kind of event" to name (Q11).

A second revision followed a **14B adversarial review** of the
plan-wide design itself (this document's current form), which raised
seven further findings before any code was written — see "14B
adversarial review findings" below. All seven are resolved in the
sections above and below; none required narrowing the ADR's scope,
only correcting its handler signature, naming, and stated guarantees.

## 14B adversarial review findings

Applied to this revision, most severe first. Each is cross-referenced
to where the fix now lives.

1. **BLOCKER — `ExecutionContext` name collision.**
   `ragtorch.core.context.ExecutionContext` (run identity/metadata,
   ADR-002) already exists and is exported. Reusing the same name for
   an unrelated results-mapping type is a long-term ambiguity hazard —
   two public types with the same bare name cannot both be imported
   under that name in the same module. **Fix**: the new type is named
   `StepExecutionContext`, not `ExecutionContext`, everywhere in this
   ADR. See "Naming" below.

2. **BLOCKER — handler received only `node_id`, not `ExecutionStep`.**
   A handler for a step with declared dependencies had no direct way
   to know what those dependencies were except by re-deriving plan
   structure the executor already had in hand. **Fix**: `StepHandler`
   now receives the full `ExecutionStep` — see Q3.

3. **BLOCKER (scoped down to a correction) — false async-compatibility
   claim.** The prior draft claimed a future async executor "can
   satisfy the same `Executor` `Protocol`." `async def execute(...)`
   returns a coroutine, not the declared return type, so this is not
   structurally true. **Fix**: retracted; `Executor` is now stated as
   explicitly synchronous-only, with an async variant left as a
   separate, differently-named future contract — see Q7.

4. **MAJOR — O(n²) context-construction cost not acknowledged.**
   Rebuilding `MappingProxyType(dict(results))` before every step
   copies the entire accumulated results dict each time, giving
   `0 + 1 + ... + (n-1)` total copy work across an n-step plan —
   quadratic, not linear, in the number of steps. **Fix**: this ADR
   does not silently accept the cost or silently re-engineer around it
   with unproven infrastructure. See "Context construction cost"
   below: v0.1 keeps the simple copy-per-step snapshot (correctness
   and a clear immutability guarantee first), and the benchmark
   (Benchmark strategy, extended to 100,000 steps) is required to
   *measure*, not assume, whether this is material before any
   persistent-structure optimization is considered as a separate,
   future ADR.

5. **MAJOR — no explicit partial-result / duplicate-`node_id` policy.**
   Two related gaps: nothing stated that `ExecutionResult` is only
   ever produced after full, successful completion (an easy invariant
   to accidentally break later by adding
   `except Exception: return ExecutionResult(...)`); and nothing
   stated the executor's reliance on `ExecutionPlan.steps` containing
   each `node_id` at most once. **Fix**: both are now explicit — see
   "Partial-result policy" and "Node-id uniqueness invariant" below,
   each with a required regression test (FAIL-04, EXEC-08).

6. **MINOR — statelessness tested via `vars(executor)`.** Tests an
   implementation detail, not the actual contract, and would fail a
   legitimate future implementation that holds unrelated instance
   state. **Fix**: restated as a behavioral cross-call-isolation
   contract — see Q9, STATE-01/STATE-02.

7. **MINOR — immutability claim imprecise.** `frozen=True` and
   `MappingProxyType` make the *mapping* immutable (no key can be
   added, removed, or reassigned through the exposed object) but say
   nothing about the *values* stored in it — a handler that stores a
   mutable object (e.g. a list) as a result and later mutates that
   object in place is not prevented by this contract. **Fix**: stated
   precisely — see "Shallow immutability" below.

All seven are BLOCKER/MAJOR/MINOR findings from a single review pass;
none required a second adversarial round, since every finding was a
correction to wording, a signature change, or an explicit-invariant
addition — not a rejection of the overall design — and none introduces
a new open question the fixes below don't already close.

## Decision

### Naming and location: `Executor`, `SequentialExecutor`, `StepExecutionContext`, `src/ragtorch/core/execution.py`

A new module, not an addition to `execution_plan.py` (a different
concern: deriving an order vs. running one) or `engine.py` (a
different concern: `Module`-bound observability vs. plan-bound
iteration). The results-mapping type is named `StepExecutionContext`,
**not** `ExecutionContext` — see 14B finding 1 — to avoid any
ambiguity with `ragtorch.core.context.ExecutionContext` (run
identity/metadata, ADR-002), an unrelated type at a different layer.
The naming is deliberately self-documenting:

```text
ExecutionContext       (ragtorch.core.context)   = run identity / metadata
StepExecutionContext   (ragtorch.core.execution) = results available to a planned step
```

### Public contract

```python
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep


@dataclass(frozen=True)
class StepExecutionContext:
    """Read-only snapshot of results produced by steps already run in
    this execute() call, keyed by node_id. Rebuilt fresh before each
    step; a handler cannot mutate it back into the executor's
    bookkeeping. The mapping itself is immutable -- the objects stored
    as values are opaque, application-owned, and are not deep-copied
    or recursively frozen (see "Shallow immutability")."""

    results: Mapping[str, object]

    @classmethod
    def from_results(cls, results: Mapping[str, object]) -> "StepExecutionContext":
        return cls(results=MappingProxyType(dict(results)))


@dataclass(frozen=True)
class ExecutionResult:
    """Every step's output from one execute() call, keyed by node_id.
    Only ever constructed after every step in the plan has completed
    successfully -- see "Partial-result policy". The mapping is
    immutable; stored values are opaque and not recursively frozen."""

    values: Mapping[str, object]

    @classmethod
    def from_values(cls, values: Mapping[str, object]) -> "ExecutionResult":
        return cls(values=MappingProxyType(dict(values)))


@runtime_checkable
class StepHandler(Protocol):
    """Caller-supplied: turns one ExecutionStep into work. The executor
    never inspects what a handler does -- it may call a Component, a
    plain function, or nothing at all."""

    def __call__(self, step: ExecutionStep, context: StepExecutionContext) -> object: ...


@runtime_checkable
class Executor(Protocol):
    """Run every step of an ExecutionPlan, in order, via handler.
    Synchronous only -- see Q7; an async variant is a separate,
    differently-named future contract, not a subtype of this one."""

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> ExecutionResult: ...


class SequentialExecutor:
    """The only Executor implementation in this version: runs plan.steps
    in order, one at a time, threading prior results forward via
    StepExecutionContext. Behaviorally stateless -- execution state
    from one execute() call never affects another; the same instance
    is reusable across repeated calls (see Q9). Thread-safety,
    reentrancy, and concurrent invocation are separate, untested
    contracts not claimed here. Does not catch handler exceptions: a
    raising handler stops the
    plan immediately and propagates the original exception object
    unmodified. Never returns a partial ExecutionResult."""

    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> ExecutionResult:
        results: dict[str, object] = {}
        for step in plan.steps:
            context = StepExecutionContext.from_results(results)
            results[step.node_id] = handler(step, context)
        return ExecutionResult.from_values(results)
```

`Executor` and `StepHandler` are `Protocol`s, not concrete classes, so
a future parallel/distributed executor, or a test handler, can satisfy
the same contract without inheriting from `SequentialExecutor` —
matching the same structural-typing precedent `Component` (ADR-010)
already established for this codebase. (A future *async* executor
does **not** satisfy `Executor` as defined — see Q7.)

### Why the plan is not re-validated or re-derived

`ExecutionPlan.steps` (ADR-017) already encodes a valid, acyclic,
dependency-respecting order — `SequentialExecutor` trusts that
guarantee rather than re-checking it, the same single-source-of-truth
discipline every prior layer in this codebase has followed.

### Node-id uniqueness invariant

`SequentialExecutor` relies on `ExecutionPlan.steps` containing each
`node_id` at most once (`results[step.node_id] = ...` assumes no prior
entry is silently overwritten with a different step's output).
`plan()` (ADR-017) derives `steps` from `CompositionGraph.nodes`,
which `CompositionGraph.__post_init__` (ADR-016) already guarantees
has no duplicate `GraphNode.id` — so this invariant is inherited, not
independently re-validated here, per the same trust-the-upstream-
guarantee discipline as above. This executor does not revalidate
uniqueness; a regression test (EXEC-08) documents and pins the
invariant rather than defensively re-checking it at runtime.

### Partial-result policy

`ExecutionResult` is produced **only** after every step in the plan
has completed successfully. There is no partial-result return
contract: if step *k* of *n* raises, no `ExecutionResult` is
constructed or returned — not for the *k-1* steps that already
succeeded, not in any other form. This is stated as a permanent
contract, not incidental current behavior, specifically so a future
change does not casually introduce
`except Exception: return ExecutionResult(partial_values)` and
silently change failure semantics that callers may already depend on
(see Q10, FAIL-04).

### Context construction cost

`StepExecutionContext.from_results` copies the accumulated `results`
dict into a fresh `MappingProxyType` before every step
(`0 + 1 + ... + (n-1)` total copy operations across an n-step plan —
quadratic in step count, not linear). This is a known, accepted cost
for this version, not an oversight (14B finding 4):

- `MappingProxyType` alone, wrapping the executor's *live* internal
  dict, would be cheap to construct but would let an already-issued
  `StepExecutionContext` observe later mutations — a dynamic view, not
  a snapshot — silently breaking the "later results are not yet
  visible to earlier steps" ordering guarantee this ADR relies on.
  Rejected for that reason, not merely because it's an option.
- An immutable persistent-map data structure (e.g. a hash-array-mapped
  trie) would make snapshotting O(1)-ish per step, but pulling in such
  infrastructure — whether hand-rolled or a new dependency — before
  any real workload has demonstrated the copy cost matters is exactly
  the kind of premature optimization this project has consistently
  rejected elsewhere (see ADR-017's Non-goals discipline).
- **Decision**: v0.1 keeps the simple copy-per-step snapshot.
  `benchmarks/step14_execution_boundary.py` is required to measure
  actual cost up to 100,000 steps and report time/step trend (see
  Benchmark strategy) specifically so this cost is *known*, not
  assumed. If the benchmark shows the quadratic term is material at
  realistic plan sizes, a persistent-result-store optimization becomes
  its own future ADR, informed by real measurements — not designed
  speculatively here.

### Shallow immutability

`StepExecutionContext.results` and `ExecutionResult.values` are
immutable **mappings**: no key can be added, removed, or reassigned
through the exposed object (`MappingProxyType` enforces this,
raising `TypeError` on attempted mutation). This says nothing about
the objects *stored as values* — a handler that returns a mutable
object (e.g. a `list` or a plain class instance) as its result, and
later mutates that same object in place, is not prevented by this
contract; values are opaque, application-owned, and are not deep-
copied or recursively frozen. Callers that need value-level
immutability are responsible for it themselves (e.g. by returning
immutable types from their handlers).

### Why failures are not wrapped here

See Q11 above.

## Non-goals

Explicitly deferred, not part of this decision:

- **`ExecutionEngine` integration.** `execution.py` does not import
  `ragtorch.core.engine`.
- **Retries, timeouts, or any other invocation policy.** See Q12/Q13.
- **Concurrency, async, or distributed execution.** Not implemented.
  `Executor` is explicitly synchronous-only (see Q7); a future async
  or concurrent executor is a separate, differently-named contract,
  not a variant of this one.
- **A provider adapter or any `Component`-specific wiring.** The
  handler is entirely caller-supplied; this ADR does not define how a
  handler resolves an `ExecutionStep` to a `Component`, nor does it
  import `ragtorch.core.component` or `ragtorch.core.composition`.
- **Serialization.** See Q15.
- **Observability beyond ordinary exception propagation.** See Q16.
- **A provider registry, sandboxing, or any new trust boundary.** See Q17.
- **A persistent/optimized result-store data structure.** See "Context
  construction cost" — deferred to a future, measurement-informed ADR
  if the benchmark shows it's needed.

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
  `StepExecutionContext`.** Rejected: allows a handler to corrupt the
  executor's own bookkeeping, and forecloses safe reuse of the
  executor across concurrent calls in the future — see Q4/Q9.
- **Give the handler only `node_id`, not the full `ExecutionStep`.**
  Rejected during 14B review — see finding 2 / Q3.
- **Claim a future async executor satisfies the same `Executor`
  `Protocol`.** Rejected during 14B review as structurally false —
  see finding 3 / Q7.
- **Reuse the name `ExecutionContext` for the new results-mapping
  type.** Rejected during 14B review — collides with
  `ragtorch.core.context.ExecutionContext` — see finding 1.
- **Return results incrementally (e.g. a generator/iterator of
  per-step results) instead of one `ExecutionResult` at the end.**
  Rejected as a needless expansion of the contract's shape before any
  consumer has demonstrated a need for streaming results; `plan.steps`
  is already available to a caller that wants to observe the handler's
  own side effects step by step.
- **Introduce a persistent/immutable-map data structure now to make
  context construction O(1)-ish per step.** Rejected for v0.1 as
  premature optimization without a measured need — see "Context
  construction cost."
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
`ragtorch.core.execution_plan` (`ExecutionPlan`, `ExecutionStep`), and
the standard library (`dataclasses`, `types.MappingProxyType`,
`typing`) — no `ragtorch.core.component`, no
`ragtorch.core.composition`, no `ragtorch.core.engine`, no provider
SDK, no persistent-map/immutable-collections package (see "Context
construction cost" for why one is not added in this version).

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ArchitectureSnapshot`, `CompositionGraph`, `GraphNode`, `Connection`,
`ExecutionPlan`, `ExecutionStep`, or `plan()` themselves.
`Executor`, `StepHandler`, `StepExecutionContext`, `ExecutionResult`,
and `SequentialExecutor` are a pure addition in a new module. Naming
`StepExecutionContext` (not `ExecutionContext`) avoids any collision
with the existing, unrelated
`ragtorch.core.context.ExecutionContext` (run identity/metadata,
ADR-002) — see "Naming" above and 14B finding 1. The exact public
export path/`__all__` membership for the new types is finalized during
implementation (14E) and recorded in the requirements matrix evidence
for A66, not left implicit.

## Testing strategy

- **CTX-01** Empty context: `StepExecutionContext.from_results({})`
  exposes an empty `results` mapping.
- **CTX-02** Context exposes previous results: a context built from
  `{"A": 1}` exposes `context.results["A"] == 1`.
- **CTX-03** Context mapping cannot be mutated:
  `context.results["A"] = ...` raises `TypeError`.
- **CTX-04** Values are not claimed to be deeply immutable: a mutable
  value (e.g. a `list`) stored as a result can still be mutated
  in-place by a holder of that reference — this is documented
  behavior (see "Shallow immutability"), verified by a test that
  mutates a returned list and confirms no error is raised, distinct
  from CTX-03's mapping-level check.
- **EXEC-01** Empty plan (`ExecutionPlan(steps=())`) returns
  `ExecutionResult(values={})` without calling `handler`.
- **EXEC-02** One step: handler is called once with that step's
  `ExecutionStep`, and `result.values` contains exactly one entry.
- **EXEC-03** Multiple steps: handler is called once per step.
- **EXEC-04** Exact execution order: handler invocation order matches
  `plan.steps` order (verified via a recording fake handler).
- **EXEC-05** The handler receives the actual `ExecutionStep` object
  from `plan.steps` (identity- or attribute-checked), not merely a
  `node_id` string.
- **EXEC-06** A later step's handler call receives a `context.results`
  containing every earlier step's already-computed value.
- **EXEC-07** `result.values` contains exactly one entry per step,
  keyed by `node_id`, with no duplicates and no missing steps.
- **EXEC-08** Node-id uniqueness invariant: a regression test
  documents (via a plan built through the normal `plan()`/
  `CompositionGraph` path) that no two steps share a `node_id`, and
  that the executor does not defensively re-check this — it relies on
  the upstream guarantee (see "Node-id uniqueness invariant").
- **Immutability**: `result.values[...] = ...` raises `TypeError`.
- **FAIL-01** Handler exception propagates out of `execute` unmodified.
- **FAIL-02** The exact exception *object* is preserved end to end:
  `error = ValueError("boom"); ...; assert exc_info.value is error` —
  stronger than checking only the exception type; proves no wrapping,
  no replacement, no swallowing.
- **FAIL-03** Downstream steps do not execute after a failure
  (verified via a recording fake handler that would record a call it
  must never actually receive for steps after the failing one).
- **FAIL-04** No partial `ExecutionResult` is returned or accessible
  after a mid-plan failure — the failure propagates as an exception,
  there is no result object to inspect at all (see "Partial-result
  policy").
- **STATE-01** Executor reusable: the same `SequentialExecutor`
  instance can call `execute` twice (different plans/handlers) and
  both calls behave identically to using two separate instances.
- **STATE-02** Execution isolation: results/context from one
  `execute()` call are not visible to or contaminated by another call
  on the same executor instance, including interleaved-looking
  sequential calls.
- **ADV-05 — plan is not mutated.** `plan == plan_before_execute` after
  `execute` returns.
- **ADV-08 — provider independence.** AST-based check: `execution.py`
  imports nothing from `ragtorch.core.component`,
  `ragtorch.core.composition`, `ragtorch.core.engine`, or any provider
  package.
- **CONTRACT-01** `SequentialExecutor` satisfies the `Executor`
  `Protocol` (`isinstance(SequentialExecutor(), Executor)`).
- **CONTRACT-02** A plain function or lambda satisfying `StepHandler`'s
  call shape works identically to a class-based handler.
- **REG-01** Regression: `CompositionGraph`, `ExecutionPlan`,
  `Sequential`, `ExecutionEngine`,
  `ragtorch.core.context.ExecutionContext`, and `Component` are all
  unmodified — the full pre-existing test suite (329 tests as of this
  ADR) passes unmodified.

## Benchmark strategy

Per ADR-009, `benchmarks/step14_execution_boundary.py`. Measures
`SequentialExecutor.execute` against a trivial handler
(`lambda step, context: step.node_id`) over plans of increasing step
count — 10 / 100 / 1,000 / 10,000 / **100,000** (extended per 14B
review, specifically to make the context-construction cost identified
in finding 4 visible at a realistic scale) — reporting, for each size:
total wall-clock time **and** time-per-step (`total_time / n`). A
roughly constant time/step across sizes is consistent with linear
behavior; a time/step that keeps growing with `n` is consistent with
the quadratic context-copying cost identified above and is the
benchmark's specific purpose to expose. This establishes a measured
baseline — it does not claim or prove an asymptotic complexity bound,
only reports measurements consistent (or not) with one, following the
same corrected methodology adopted for Step 13's benchmark and
evaluation report. If the results show the quadratic term dominates at
realistic plan sizes, that finding is recorded in
`evaluation/step14-evaluation.md` and treated as an input to a future,
separate ADR — not silently fixed by scope-creeping this one.

## Consequences

- Step 14 delivers a genuine plan-runner boundary: any caller with an
  `ExecutionPlan` and a way to turn an `ExecutionStep` into work can
  run the whole plan today, without waiting on `ExecutionEngine`
  integration or a provider adapter.
- Provider independence is structural: `execution.py` cannot import
  `Component`, `CompositionGraph`, or any provider, by construction —
  enforced by ADV-08, not merely by convention.
- The executor's behavioral statelessness and immutable
  `StepExecutionContext`/`ExecutionResult` are deliberately chosen now
  so a future concurrent executor does not have to retrofit these
  properties under a compatibility constraint.
- Failure semantics are deliberately *not* unified with
  `Module.__call__`'s `ExecutionError` wrapping in this version — a
  considered trade-off (Q11), not an oversight; a handler that wants
  `ExecutionError` semantics raises one itself. The original exception
  object is guaranteed to propagate unmodified (FAIL-02), and no
  partial result is ever produced on failure (see "Partial-result
  policy").
- The context-construction cost is a known, measured (not assumed)
  trade-off for v0.1 simplicity; the benchmark is the mechanism that
  keeps this honest rather than aspirational — see "Context
  construction cost."
- Naming (`StepExecutionContext`, not `ExecutionContext`) avoids a
  public-API collision that would have been expensive to fix after
  release — see 14B finding 1.
- The async-compatibility claim retracted in this revision (14B
  finding 3) keeps the ADR's stated guarantees accurate rather than
  aspirational, consistent with this project's standing rule that a
  benchmark or contract must describe what is actually true, not what
  would be convenient to claim.
- Scope stays deliberately narrow: no `ExecutionEngine` integration, no
  retries, no timeouts, no concurrency, no provider adapter, no
  persistent result-store optimization — consistent with every prior
  step's discipline.
