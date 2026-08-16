# ADR-018: Step Execution Boundary

## Status

Proposed

## Context

After Step 13, `ExecutionPlan` (ADR-017) can answer "given a valid
`CompositionGraph`, in what deterministic order should its nodes run,
and what does each node depend on?" — but nothing in the codebase yet
answers "how does invoking *one* planned node actually happen?"
`ExecutionStep.node_id` names a `GraphNode.id`; `CompositionGraph`
(ADR-016) is the only existing structure mapping that id to a real
`Component` instance; and `ExecutionPlan` deliberately does not retain
a reference to the graph it was derived from (ADR-017), so something
between "I have a plan" and "components actually ran" must resolve
identity, supply inputs, invoke the component, and surface the result
or failure — without becoming a second `ExecutionEngine`, without
knowing anything about providers, and without prematurely deciding
scheduling, concurrency, retries, or observability.

`ExecutionEngine` (ADR-006/ADR-008) already exists and is bound to
`Module`, not `Component`/`ExecutionStep` — it coordinates
`Run`/`Trace`/`MetricsCollector` around a single `Module.__call__` and
re-raises failures after recording them (verified by reading
`engine.py`: `except Exception as exc: run.fail(exc); ...; raise`).
`Component` (ADR-010) remains deliberately minimal — `name`,
`component_type`, `__call__(input, *, context=None)` — with zero
provider or scheduling awareness. `Module.__call__` (Step 1) already
establishes a wrapping convention for component-level failures: every
exception except `RegistryError` is re-raised as
`ExecutionError(...) from exc` (verified in `module.py`), used and
tested across more than a dozen existing test files. `docs/architecture/v0.1-architecture.md`
§2 already names "Runtime" as the layer that "executes an architecture
and owns execution identity, scheduling semantics, lifecycle, error
propagation, policies, and observability integration" — separate from
component business logic — so this ADR's boundary is not a new
invention, it is the first concrete piece of that already-named layer.

**This ADR does not build a plan runner, a scheduler, concurrency, or
`ExecutionEngine` integration.** It answers one narrower question: given
one `ExecutionStep`, its resolved `Component`, its resolved input
value(s), and an `ExecutionContext`, what is the smallest stable,
provider-independent contract for invoking that single step and
surfacing its result or failure? Confirmed with the project owner
before drafting, following an 18-question audit (14A) grounded in
direct inspection of `component.py`, `context.py`, `engine.py`,
`ports.py`, `composition.py`, `execution_plan.py`, and `errors.py` —
not assumed from memory.

```text
CompositionGraph (ADR-016)
      |
      v
ExecutionPlan (ADR-017) -- WHAT order, WHAT depends on WHAT
      |
      v
StepExecutor (this ADR) -- HOW one step is invoked
      |
      v
Component (ADR-010)
      |
      v
provider / model / retriever / etc.

Future, independent of this ADR:
  PlanRunner    -- orchestrates MANY steps using StepExecutor
  ExecutionEngine -- Run/Trace/Metrics, currently bound to Module
```

## Problem

We need a minimal, provider-independent contract for invoking one
already-identified `Component` with one already-resolved input value,
under an explicit `ExecutionContext`, that (a) does not resolve
`node_id -> Component` itself (that stays the caller's/future
`PlanRunner`'s responsibility, since `ExecutionPlan` does not retain
the graph), (b) does not schedule, retry, time out, or run
concurrently, (c) does not duplicate `ExecutionEngine`'s
observability responsibility, and (d) fails loud with a consistent,
already-established exception convention rather than a new one.

## Open questions this ADR must decide before any code is written

The 14A audit raised 18 questions, following the same discipline
ADR-017 established. Each is given an explicit decision below, with
the rejected alternative stated, not merely the chosen answer.

**Q1 — What exactly is being executed?** An `ExecutionStep` identifies
*which* node (`node_id`) and its declared direct dependencies; the
`Component` to invoke is resolved by the caller (see Q3) before
calling the executor. The executor's contract operates on a resolved
`Component` plus the `ExecutionStep` that named it — not on the
`GraphNode`, not on the raw `node_id` alone, and not on `CompositionGraph`.

**Q2 — Does the executor receive the `Component` directly, or resolve
it itself?** Directly. Rejected: having the executor perform
`node_id -> Component` resolution itself, which would require it to
either hold a `CompositionGraph` reference (reopening ADR-017's
explicit non-retention decision one layer up) or invent a second
node-registry concept duplicating `CompositionGraph.nodes`. The
executor's contract takes an already-resolved `Component` as an
explicit argument; something else (a future `PlanRunner`, or a test,
or any caller) performs the lookup against the `CompositionGraph` it
already has in scope.

**Q3 — Where does node lookup happen?** Outside this ADR's scope,
performed by the caller using `CompositionGraph.nodes` directly (a
`tuple[GraphNode, ...]`, already searchable by `id`). This ADR does
not introduce an executor registry, an execution runtime, or any new
id-to-component mapping — `CompositionGraph` remains the single source
of truth for that mapping, per the same single-source-of-truth
discipline every prior layer in this codebase has followed.

**Q4 — Where do inputs come from, and what shape are they?** A single
opaque `object` value per step, supplied by the caller — not a
`Mapping[str, object]` keyed by dependency node id, and not a
port-keyed structure. Rejected: reusing `InputPort`/`OutputPort` for
runtime value routing, since ports (ADR-011) are deliberately static
*metadata* (`name`, `type`), never runtime values, and reusing them for
this purpose would silently expand their scope beyond what ADR-011
committed to. Rejected: a `Mapping[str, object]` of all upstream
outputs, since deciding *how* a step with multiple dependencies
combines their outputs into one input value is exactly the kind of
component-specific aggregation semantics ADR-016 already deferred for
`CompositionGraph`'s fan-in rule (see ADR-016 "Cardinality") — this
executor boundary does not silently reopen that deferral by picking an
input-shape convention that presumes an answer. The executor accepts
one input value per invocation; how a future `PlanRunner` produces
that one value from a step's dependencies (pass-through for a single
dependency, an explicit merge step for multiple) is that runner's
decision, not this ADR's.

**Q5 — Where do outputs go?** The executor returns the `Component`'s
raw output value directly — not wrapped in an `ExecutionValue`, not
keyed by node id, not stored anywhere. The executor's contract is a
single invocation, not a plan-wide result store; a future `PlanRunner`
that needs `node_id -> output` bookkeeping across an entire plan owns
that structure itself, built from repeated calls to this executor.

**Q6 — Does this ADR execute multiple nodes / a whole plan?** No.
Explicitly out of scope — see Non-goals. This ADR establishes the
single-step invocation boundary only; a `PlanRunner` that walks
`ExecutionPlan.steps` and calls this executor once per step,
respecting dependency order, is deliberately deferred to a future step.

**Q7 — Sync or async?** Synchronous in this version. The contract is
written so a future async variant is additive (a distinct
`async def execute` on a separate protocol, or a distinct
implementation), not a breaking change to this one — see "Future
extensibility" below. No `Awaitable`/`async` is introduced now, since
no consumer of this boundary requires it yet and introducing it
without a real async component to test against would be exactly the
kind of speculative API this project has consistently avoided.

**Q8 — Does the executor know about providers?** No. Not contested —
`Component` (ADR-010) already has zero provider awareness; this
executor's contract operates purely in terms of `Component`,
`ExecutionStep`, and `ExecutionContext`, none of which mention any
provider, model, or vendor SDK.

**Q9 — Does the executor depend on `ExecutionEngine`?** No.
`execution.py` (this ADR's module) will not import
`ragtorch.core.engine`. The dependency direction remains one-way:
`ExecutionPlan` -> step executor -> `Component`, entirely independent
of `ExecutionEngine` -> `Run`/`Trace`/`Metrics`. Connecting the two is
explicit future work (see Non-goals), not assumed or implied by this ADR.

**Q10 — Failure behavior: swallow or propagate?** Propagate. Not
contested — every existing execution-adjacent boundary in this
codebase (`Module.__call__`, `ExecutionEngine.execute`) re-raises
after recording/wrapping, never returns a sentinel or a
`Result(success=False)` object. This executor follows the same rule:
a component's exception is never silently converted into a return
value.

**Q11 — Should failure information be wrapped, and how?** Wrapped in
`ExecutionError`, via `raise ExecutionError(...) from exc` — **matching
`Module.__call__`'s existing, established convention exactly**, found
during the 14A audit (`module.py`: `raise ExecutionError(f"Module
{self._name!r} raised {type(exc).__name__}: {exc}") from exc` for
every exception except `RegistryError`). This was a genuine decision
point, not a formality: an earlier draft of this audit favored
preserving the original exception type unwrapped, for callers that
want to catch a specific provider exception. That preference is
rejected here in favor of consistency: this codebase already has
exactly one established failure-wrapping convention for "a
component/module raised during invocation," and introducing a second,
different one (unwrapped) for `Component`/`ExecutionStep` invocation
would mean two different things happen depending on whether a
component is invoked via `Module.__call__` or via this new executor —
for what is conceptually the same kind of event. `raise ... from exc`
preserves the original exception via `__cause__`, so a caller that
truly needs the original type can still access `exc.__cause__` or
inspect the chain; `except RAGTorchError:` (or `except ExecutionError:`)
continues to catch every execution failure uniformly across the
framework, exactly as it already does for `Module`.

**Q12 — Retry?** Not in this ADR. No `retry=N`/backoff parameter.
Retry semantics differ radically by component (a network call retries
differently than a local computation), and a generic retry policy
imposed at this layer would presume an answer no real component has
yet demonstrated a need for. Deferred to a future policy layer — see
Non-goals.

**Q13 — Timeout?** Not in this ADR, for the same reason as Q12, plus:
a generic timeout mechanism raises unresolved questions (thread vs.
async cancellation, partial side effects, cleanup) this ADR has no
basis to answer yet. Deferred — see Non-goals.

**Q14 — Concurrency?** Not implemented, but not foreclosed.
`ExecutionStep.dependencies` (ADR-017) already carries exactly the
information a future concurrent scheduler needs to determine
readiness; this ADR's contract (one step, one call, synchronous) does
not prevent a future `PlanRunner` from calling multiple independent
executors concurrently — it just does not implement or expose that
here.

**Q15 — Serialization?** Not implemented. The executor's *contract*
(a `Component`, an `ExecutionStep`, an `ExecutionContext`, an input
value, an output value) is not itself a data structure to serialize —
it is a call shape. Nothing about this ADR requires `ExecutionPlan`'s
existing serialization-friendliness (ADR-017) to change, since the
executor never becomes part of a plan's data.

**Q16 — Observability?** Not owned by the step executor in this
version. `ExecutionEngine` already owns `Run`/`Trace`/`Metrics`
end-to-end for `Module`; duplicating any part of that responsibility
here — even partially — would create two competing observability
paths for what should eventually be one execution story. Connecting
`ExecutionEngine`'s observability to step-level execution is
explicit, deliberately deferred future work (see Non-goals), not
solved by inventing a smaller, parallel observability mechanism now.

**Q17 — Security / trust boundary?** Component invocation is trusted
application code, exactly as it already is for `Module.__call__` and
`ExecutionEngine.execute` — this ADR introduces no new trust boundary,
no sandboxing, and no restriction on what a `Component` may do once
invoked. Sandboxing untrusted component code, if ever needed, is an
entirely different, unrelated security boundary this ADR does not
address.

**Q18 — API stability: what is the smallest contract confident enough
to freeze now?** A single-method `Protocol` (see Public contract
below) taking exactly `Component`, `ExecutionStep`, `ExecutionContext`,
and one input value, returning one output value, raising
`ExecutionError` on failure. No scheduler, worker, thread pool, retry
policy, timeout policy, provider registry, serialization, or
distributed-execution concept is exposed — each is explicitly a
Non-goal, not implied by the shape of this contract.

## Decision

### Naming and location: `StepExecutor`, `src/ragtorch/core/execution.py`

A new module, not an addition to `execution_plan.py` (a different
concern: deriving an order vs. invoking one step) or `engine.py` (a
different concern: `Module`-bound observability vs. `Component`-bound
invocation). `execution.py` (not `executor.py` or `runner.py`) names
the concern this module owns — invocation — without presuming the
name of a future plan-level runner.

### Public contract

```python
@runtime_checkable
class StepExecutor(Protocol):
    """Invoke one ExecutionStep's Component with one input value.

    Does not resolve node_id -> Component (the caller supplies an
    already-resolved Component). Does not schedule, retry, time out,
    or run concurrently. Does not know about ExecutionEngine or any
    provider. Raises ExecutionError (from the original exception, via
    `from exc`) if the component raises, matching Module.__call__'s
    existing convention exactly -- never returns a sentinel or
    swallows a failure.
    """

    def execute(
        self,
        step: ExecutionStep,
        component: Component[object, object],
        input: object,
        *,
        context: ExecutionContext,
    ) -> object:
        """Invoke component(input, context=context) for the given step.

        Returns the component's raw output value. Raises ExecutionError
        (chained via `from exc`) if the component raises any exception.
        """
        ...


class DefaultStepExecutor:
    """The only StepExecutor implementation in this version: a direct,
    synchronous call to component(input, context=context), wrapped in
    the standard ExecutionError convention. No hidden scheduling,
    retry, timeout, or observability -- exactly what the Protocol
    promises and nothing more."""

    def execute(
        self,
        step: ExecutionStep,
        component: Component[object, object],
        input: object,
        *,
        context: ExecutionContext,
    ) -> object:
        try:
            return component(input, context=context)
        except Exception as exc:
            raise ExecutionError(
                f"Step {step.node_id!r} raised {type(exc).__name__}: {exc}"
            ) from exc
```

`StepExecutor` is a `Protocol`, not only a concrete class, so a future
async variant, a future instrumented variant (once `ExecutionEngine`
integration is deliberately designed), or a test double can all
satisfy the same contract without inheriting from `DefaultStepExecutor`
— matching the same structural-typing precedent `Component` (ADR-010)
already established for this codebase.

### Why `step` is a parameter even though only `step.node_id` is used

`DefaultStepExecutor.execute` uses only `step.node_id` (for the error
message) today, not `step.dependencies` — but the `Protocol` accepts
the full `ExecutionStep`, not a bare `node_id: str`, because a future
implementation (e.g. one that validates that the supplied `input`
actually corresponds to `step.dependencies`, or that attaches
dependency information to a wrapped error) can use the richer object
without changing the contract's shape. This mirrors the same
"richer form over a bare primitive" reasoning ADR-017 applied to
`ExecutionStep` over a plain `str`.

### Why failure wrapping matches `Module.__call__` exactly

See Q11 above for the full reasoning. Concretely, `raise
ExecutionError(f"Step {step.node_id!r} raised {type(exc).__name__}:
{exc}") from exc` mirrors `module.py`'s `raise ExecutionError(f"Module
'{self._name}' raised {type(exc).__name__}: {exc}") from exc` in
every respect except substituting the step's node id for the module's
name — this is a deliberate parallel, not a coincidence, so a reader
already familiar with `Module`'s failure convention needs to learn
nothing new here. `RegistryError` is not special-cased here as it is
in `Module.__call__`, because `RegistryError` ("module registration is
invalid") has no meaning at the `Component`/`ExecutionStep` level —
there is no registration concept in this boundary to raise it for.

### `input` is a single opaque value, not a mapping

See Q4 above. This is the most consequential open question in this
ADR — deliberately not resolved by inventing an input-aggregation
convention this ADR has no basis to justify.

## Non-goals

Explicitly deferred, not part of this decision:

- **A plan runner.** Nothing here walks `ExecutionPlan.steps` or
  executes more than one step. A future `PlanRunner` (or similarly
  named type) that does so, calling `StepExecutor.execute` once per
  step in dependency order, is deliberately separate future work.
- **`ExecutionEngine` integration.** `execution.py` does not import
  `ragtorch.core.engine`; `ExecutionEngine` is not modified to accept
  or produce a `StepExecutor`/`ExecutionStep`.
- **Retries, timeouts, or any other invocation policy.** Explicitly
  out of scope — see Q12/Q13.
- **Concurrency or async execution.** Not implemented; the contract is
  written not to foreclose either — see Q7/Q14.
- **`node_id -> Component` resolution as part of this contract.**
  Remains the caller's responsibility, using `CompositionGraph.nodes`
  directly — see Q2/Q3.
- **Multi-dependency input aggregation semantics.** How a step with
  more than one dependency combines those outputs into one input value
  is not decided here — see Q4.
- **Serialization.** Not implemented; not applicable to a call-shape
  contract — see Q15.
- **Observability beyond re-raising a wrapped exception.** No
  `Run`/`Trace`/`Metrics` integration — see Q16.
- **A provider registry, sandboxing, or any new trust boundary.** See Q17.

## Alternatives considered

- **Have the executor resolve `node_id -> Component` itself (accept a
  `CompositionGraph` or a registry).** Rejected: would either reopen
  `ExecutionPlan`'s explicit non-retention-of-graph decision one layer
  up, or invent a second node-registry concept duplicating
  `CompositionGraph.nodes` — see Q2/Q3.
- **Accept `Mapping[str, object]` of all dependency outputs as
  input.** Rejected: presumes an aggregation-semantics answer this ADR
  has no basis to give, mirroring ADR-016's deliberate deferral of
  fan-in aggregation semantics — see Q4.
- **Preserve the original exception type unwrapped, rather than
  wrapping in `ExecutionError`.** Rejected after finding
  `Module.__call__`'s existing, tested convention during the 14A
  audit: introducing a second, different failure convention for
  conceptually the same kind of event (a component raised during
  invocation) would be inconsistent, not merely a stylistic choice —
  see Q11.
- **Make `StepExecutor` a concrete base class, not a `Protocol`.**
  Rejected: `Component` (ADR-010) already establishes structural
  typing as this codebase's convention for "things that can be
  swapped without inheritance"; a `Protocol` here is consistent with
  that precedent and keeps a future async or instrumented executor
  from being forced into an inheritance hierarchy.
- **Introduce retry/timeout parameters now, defaulted to off.**
  Rejected: even an off-by-default parameter freezes an API shape
  (and a semantic promise about what "on" would mean) before any real
  component has demonstrated what retry/timeout semantics it actually
  needs — see Q12/Q13, and the project's standing "freeze only what
  we have enough evidence to make stable" principle.

## Security

`StepExecutor.execute` (both the `Protocol` and `DefaultStepExecutor`)
performs exactly one operation with external effect: calling
`component(input, context=context)`. It introduces no new trust
boundary beyond what `Module.__call__`/`ExecutionEngine.execute`
already establish (component invocation is trusted application code),
no dynamic import, no `eval`/`exec`, no network operation of its own,
no deserialization, and no new credential or resource handling.

## Dependency review

Zero new runtime dependencies. `execution.py` imports
`ragtorch.core.component` (`Component`), `ragtorch.core.context`
(`ExecutionContext`), `ragtorch.core.errors` (`ExecutionError`),
`ragtorch.core.execution_plan` (`ExecutionStep`), and the standard
library `typing` (`Protocol`, `runtime_checkable`) — no `networkx`, no
scheduler/workflow package, no provider SDK.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `CompositionGraph`,
`GraphNode`, `Connection`, `ExecutionPlan`, `ExecutionStep`, or `plan()`
themselves. `StepExecutor`/`DefaultStepExecutor` are a pure addition,
in a new module.

## Testing strategy

- Unit: `DefaultStepExecutor.execute` invokes a fake `Component` with
  the given input and context, and returns its raw output unmodified.
- Unit: `context` is passed through to `component(...)` exactly as
  given (identity-checked, not merely equality-checked).
- Unit: `input` is passed through to `component(...)` exactly as given.
- Unit: a component whose `__call__` raises `ValueError` results in
  `ExecutionError` being raised, with the original `ValueError`
  accessible as `exc.__cause__` and the step's `node_id` present in
  the message (mirroring `Module.__call__`'s existing test pattern in
  `test_module.py`/`test_engine.py`).
- Unit: `DefaultStepExecutor` does not swallow any exception type,
  including `RAGTorchError` subclasses raised by the component itself
  (they are still wrapped in `ExecutionError`, not re-raised as-is —
  no `RegistryError`-style special case exists at this layer, unlike
  `Module.__call__`, since `RegistryError` has no meaning here).
- Contract: a component satisfying only the `Component` `Protocol`
  (no inheritance from `Module` or any `ragtorch` base class) works
  identically to a `Module`-based component through `StepExecutor`,
  reusing the same non-`Module` test-double pattern ADR-010 already
  established.
- Contract: `DefaultStepExecutor` itself satisfies the `StepExecutor`
  `Protocol` (`isinstance(DefaultStepExecutor(), StepExecutor)`).
- Failure: missing/`None` `context` is rejected by the type contract
  (no `context: ExecutionContext | None = None` default here, unlike
  `Component.__call__`) — a caller must always supply an explicit
  context, since a step executor has no reasonable "no context" case
  the way a bare `Module` call might.
- Provider-independence: no provider import in `execution.py`
  (AST-based check, reusing the established pattern).
- No `ExecutionEngine` import: dedicated AST-based check, reusing the
  pattern established in Step 13's `test_execution_plan_module_does_not_import_execution_engine`.
- Regression: `CompositionGraph`, `ExecutionPlan`, `Sequential`,
  `ExecutionEngine`, `ExecutionContext`, and `Component` are all
  unmodified — the full pre-existing test suite passes unmodified.

## Benchmark strategy

Per ADR-009, `benchmarks/step14_execution_boundary.py`. Measures a raw
`component(input, context=context)` call against
`DefaultStepExecutor.execute(step, component, input, context=context)`
for the same component, at increasing call counts (1/10/100/1,000/10,000
where meaningful), reporting the overhead the wrapping adds (expected:
small and roughly constant per call — one `try`/`except` frame and one
`ExecutionStep` attribute access on the success path). No hard
threshold asserted, consistent with prior benchmarks' methodology; a
benchmark shows measurements consistent (or not) with an overhead
claim, it does not prove one.

## Consequences

- A future `PlanRunner` has a ready-made, already-tested single-step
  invocation boundary to call once per `ExecutionStep`, without
  needing to invent component-invocation-plus-failure-wrapping itself.
- The failure-handling story across the framework stays uniform:
  `Module.__call__` and `StepExecutor.execute` both raise
  `ExecutionError` via `from exc` for the same conceptual event (a
  component/module raised during invocation) — one convention, not two.
- Scope stays deliberately narrow: no plan runner, no
  `ExecutionEngine` integration, no retries, no timeouts, no
  concurrency, no input-aggregation semantics — consistent with every
  prior step's discipline, and explicitly informed by a code-grounded
  18-question audit rather than an untested draft preference (see Q11
  for the one place that audit changed the intended design).
