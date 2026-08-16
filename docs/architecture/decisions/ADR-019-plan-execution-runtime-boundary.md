# ADR-019: Plan Execution Runtime Boundary

## Status

Proposed

## Context

Step 14 (ADR-018) built `Executor`/`SequentialExecutor`, which runs an
`ExecutionPlan` (ADR-017) via a caller-supplied `StepHandler`, but
deliberately stops short of any runtime-lifecycle concern:
`SequentialExecutor.execute` creates no `Run`, no `Trace`, no metrics,
and imports nothing from `ragtorch.core.engine` — see ADR-018
Non-goals ("ExecutionEngine integration"). `ExecutionEngine`
(ADR-006/ADR-008) already provides that lifecycle, but only for a
single `Module` call: `execute(module, input, context=None) ->
ExecutionResult` creates a `Run`, a `Trace`, a `MetricsCollector`,
optionally records a span, records a duration metric, and re-raises
any failure after recording it. Nothing today connects the two: a
caller who has both an `ExecutionPlan` and wants engine-owned
`Run`/`Trace`/`Metrics` around running it has no API to call.

`docs/architecture/v0.1-architecture.md` §"Runtime" already names this
boundary's intended shape: "Executes an architecture and owns
execution identity, scheduling semantics, lifecycle, error
propagation, policies, and observability integration" — so this ADR
is the first concrete piece of that already-named layer to touch plan
execution specifically, not a new invention.

Grounded in direct inspection (15A/15B audit) of `engine.py` (full
file), `run.py` (full file), `trace.py` (full file), `metrics.py`
(full file), `context.py` (full file), `sequential.py` (full file),
and `tests/integration/test_nested_execution.py` (full file) — not
assumed from memory. Confirmed via direct grep that A66 is the highest
existing requirements-matrix ID before allocating A67.

**This ADR does not change `ExecutionEngine.execute(module, ...)`,
does not add async/parallel/distributed execution, does not add
retries/timeouts, and does not make the engine derive plan order or
resolve `node_id -> Component` itself.** It answers one question:
given an `ExecutionPlan` and a `StepHandler` (ADR-018), what is the
smallest additive `ExecutionEngine` entry point that wraps
`Executor.execute` with the same `Run`/`Trace`/`Metrics` lifecycle
guarantee `execute(module, ...)` already provides for a single
`Module` call — without becoming a second planner, a second executor,
or a scheduler?

```text
CompositionGraph (ADR-016)
      |
      v
ExecutionPlan (ADR-017) -- WHAT order, WHAT depends on WHAT
      |
      v
Executor / SequentialExecutor (ADR-018) -- HOW steps are iterated
      |
      v
StepHandler (caller-supplied, ADR-018) -- turns one ExecutionStep into work
      |
      v
Component / provider / model / retriever / etc. (caller's choice)

This ADR adds:

ExecutionEngine.execute_plan(plan, handler, ...) (this ADR)
      |
      v
Run / Trace / MetricsCollector -- lifecycle, owned by the engine
      |
      v
delegates iteration entirely to Executor.execute(plan, handler)
```

## Problem

We need a minimal, additive `ExecutionEngine` entry point for running
an `ExecutionPlan` under the same lifecycle guarantee
`execute(module, ...)` already gives a single `Module` call — one
`Run`, one `Trace`, plan-level metrics, failure re-raised after being
recorded — while (a) not touching `execute(module, ...)` at all, (b)
not deriving plan order or resolving steps to work itself (that stays
`Executor`'s and the handler's job), (c) not silently widening
`StepHandler`'s already-Accepted signature to inject per-step runtime
context, and (d) not silently inheriting the audit-confirmed gap that
today's `execute(module, ...)` has no protection against observability
itself raising.

## Open questions this ADR must decide before any code is written

**Q1 — Does `execute_plan` replace or coexist with
`execute(module, ...)`?** Coexists, unconditionally additive.
`execute(module, ...)`'s signature, behavior, and every existing test
remain byte-for-byte unchanged — verified by COMPAT-01 (see Testing
strategy). Rejected: folding plan support into `execute` via
overloading or an `isinstance` branch, which would couple two
unrelated call shapes (`Module` vs. `ExecutionPlan`+`StepHandler`) into
one method signature for no benefit — a new method name is strictly
simpler and matches this codebase's existing preference for explicit,
narrow contracts over polymorphic ones (e.g. `Component`'s Protocol
being separate from `Module`, not merged into it).

**Q2 — How does `execute_plan` give the handler access to a per-step
`ExecutionContext`?** **It does not — and, critically, the root
`ExecutionContext` `execute_plan` creates when `context=None` is not
reachable by the caller's handler at all.** `StepHandler.__call__(step,
context: StepExecutionContext) -> object` (ADR-018) is already
Accepted, frozen public API, with no parameter for `ExecutionContext`.
This ADR adopts, as an explicit policy (found necessary during 15D
adversarial review — see ADV-01), **option A: `ExecutionContext`
propagation into step work is out of scope for this API entirely.**
`ExecutionContext` in `execute_plan` exists solely for engine-owned
lifecycle identity and observability (`Run.context`, span attribution)
— it is not, and this version does not attempt to make it, a channel
for delivering run identity to the handler or to whatever the handler
internally invokes. Concretely: `engine.execute_plan(plan, handler)`
with no `context=` argument creates a root `ExecutionContext`
internally that `handler` has no way to obtain — this is a deliberate
consequence of the policy, not an oversight, and is stated here so a
future reader does not reasonably-but-wrongly assume that supplying
`context=ExecutionContext(metadata={...})` causes components invoked
inside `handler` to receive that context. It does not. Rejected
alternatives for closing this gap, in order of consideration: (a)
widening `StepHandler`'s signature — a breaking change to an
already-Accepted contract this ADR has no standing to make
unilaterally; (b) an implicit side-channel (thread-local, mutable
attribute) for context propagation, which this project has never used
elsewhere and which would introduce exactly the kind of "global
mutable execution state" `ExecutionContext` was originally designed to
avoid (see `context.py`'s own docstring: "without relying on
process-wide global state"); (c) requiring `context` always be
caller-supplied so at least the caller (not the engine) holds a
reference usable when building `handler` — rejected because it does
not actually solve the reachability problem (the caller still cannot
get the engine's *per-call* context into a handler built *before* the
call, only reuse whatever they passed in) and would remove the
zero-configuration default `execute(module, ...)` already has. If a
caller's handler needs run identity (e.g. because it internally
invokes a `Component`), the caller must construct that identity
themselves, independent of `execute_plan`'s own root `ExecutionContext`
— for example, by building a root `ExecutionContext` beforehand,
closing over `context.child(node_id=...)` inside their own handler
function (mirroring `Sequential.forward`'s existing
`context.child(step=f"step{i}")` pattern), and *also* passing that same
context object as `execute_plan`'s `context=` argument so `Run.context`
and the handler's derived contexts share a common root — that
composition is entirely the caller's responsibility, not something
this API wires together.

**Q3 — Who creates the `Run`?** `ExecutionEngine.execute_plan`, exactly
as `execute(module, ...)` already creates one `Run` per call — not
`SequentialExecutor` (which remains stateless and lifecycle-unaware
per ADR-018), and not the caller.

**Q4 — Do `ExecutionContext` and `StepExecutionContext` merge?** No.
Confirmed unchanged from ADR-018's own decision: `ExecutionContext`
(run identity/metadata, `ragtorch.core.context`) and
`StepExecutionContext` (per-step prior results,
`ragtorch.core.execution`) remain distinct types at distinct layers,
composed by a caller when needed, never merged into one object. This
ADR does not add a third context type.

**Q5 — Does `StepHandler`'s signature change?** No — see Q2. This is
the most consequential decision in this ADR: rather than assume a
wrapping mechanism, the audit-confirmed absence of an `ExecutionContext`
slot in the already-Accepted `StepHandler` contract is treated as a
hard constraint, not an implementation detail to work around.

**Q6 — What triggers a per-step child `ExecutionContext`, if the
engine doesn't create one?** Nothing, in this ADR — and, per Q2's
option A, `execute_plan` does not even make its own root context
reachable by `handler`. `Sequential`'s `context.child(step=f"step{i}")`
precedent remains real and directly informs how a *caller* might build
a context-aware handler entirely on their own, using a context object
of their own construction, but `execute_plan` itself neither replicates
that derivation nor supplies the raw material for it to the handler —
see Q2.

**Q7 — How many spans does `execute_plan` create, and what is the
span named?** Exactly one for the whole plan-level call, at `DEBUG`
observability level — mirroring `execute(module, ...)`'s existing
behavior exactly, and consistent with ADR-007's already-tested
non-goal for `Sequential` (`test_engine_full_rag_shaped_pipeline`
asserts `len(result.trace.spans) == 1` even for a 3-stage nested
pipeline). **Frozen during 15D adversarial review (see ADV-03)**: the
span's `name` is the fixed literal string `"execute_plan"` — not
derived from the plan, the executor's type, or any per-call value.
This mirrors `execute(module, ...)`'s own span-naming convention
structurally (a fixed, predictable identifier an observability
consumer can match on), while necessarily differing in content since a
plan has no `Module.name`/`type(module).__name__` to borrow the way
`execute(module, ...)` does. The span carries **no automatic
attributes** beyond what `Trace.start_span` already attaches
(`run_id`, matching `execute(module, ...)`'s `_maybe_span` call
exactly) — no plan size, no executor type, no step count — consistent
with Q14's "no automatic payload/metadata capture" decision. Per-step
spans are an explicit Non-goal — not silently foreclosed, but not
something this ADR's audit found evidence justifying, and adding them
would reopen ADR-007's settled non-goal without new justification.

**Q8 — What is the observable "execution unit" for tracing purposes?**
One `execute_plan()` call — matching "one `execute()` call" today, not
`ExecutionStep`, not "one handler invocation." Consistent with Q7.

**Q9 — How does handler failure interact with the `Run`?**
`execute_plan` catches the propagating exception from
`Executor.execute` at exactly the same point `execute(module, ...)`
catches a `Module.__call__` exception: `run.fail(exc)`, record
duration, then a bare `raise` — no `from exc`, no new wrapping, an
exact structural mirror of `execute(module, ...)`'s existing
`except Exception as exc: run.fail(exc); ...; raise`. The exception
that propagates out of `execute_plan` is the same object
`Executor.execute` raised — which, per ADR-018, is itself the
handler's original, unwrapped exception. No new exception type or
wrapping is introduced at either layer.

**Q10 — Does `execute_plan` ever swallow a failure?** No — not
contested. Matches every existing execution-adjacent boundary in this
codebase.

**Q11 — Does `execute_plan` derive plan order or resolve steps
itself?** No. It receives an already-built `ExecutionPlan` and
delegates all iteration to the `Executor` it is given — see Q12. It
does not import `ragtorch.core.composition` and does not walk
`plan.steps` itself.

**Q12 — Is the `Executor` caller-supplied or engine-owned?**
Caller-suppliable, defaulting to `SequentialExecutor()` if omitted.
`execute_plan(plan, handler, *, context=None, executor=None)` accepts
an `Executor | None`. **Corrected during 15D adversarial review (see
ADV-02)**: `executor`'s substitutability is compatible with any future
**synchronous** `Executor` implementation satisfying ADR-018's
`Protocol` (e.g. a future `ParallelExecutor` that still returns
`StepExecutionResult` synchronously) — not, as an earlier draft of
this ADR incorrectly claimed, a future *asynchronous* executor.
ADR-018 already established that `async def execute(...)` cannot
structurally satisfy `Executor` (it returns a `Coroutine`, not a
`StepExecutionResult`), and `execute_plan` itself is synchronous only
(Q16) — so no asynchronous executor could ever be passed to this
parameter under this ADR's contract, regardless of what
`Executor`-substitutability might suggest in isolation. A future
asynchronous engine entry point would require its own, separately
defined async contract (an `async def execute_plan` or equivalent on
a distinct type), not a variant of this one. Rejected: hard-coding
`SequentialExecutor` internally with no override, which would make a
future synchronous alternative (e.g. `ParallelExecutor`) require
engine changes to use — exactly the coupling ADR-018's `Executor`
`Protocol` exists to avoid. Rejected: requiring the caller to always
supply one, which would make the common case (`SequentialExecutor`,
the only implementation that currently exists) more verbose than
`execute(module, ...)`'s zero-configuration default.

**Q13 — What does `execute_plan` measure, and under what exact
name?** One plan-level duration metric — not one metric per step.
**Frozen during 15D adversarial review (see ADV-04)**: the metric name
is the fixed literal string `"execution_plan.duration_s"`, chosen to
be exact and dashboard-stable rather than the vague
`{engine-scoped name}.duration_s` an earlier draft of this ADR left
underspecified. `execute(module, ...)`'s existing metric naming
(`f"{module_name}.duration_s"`, derived from `type(module).__name__`)
is unchanged and untouched by this decision — `execute_plan` does not
attempt to borrow or generalize that per-module naming scheme, since a
plan has no single module name to derive one from, and inventing a
derived name (e.g. from the executor's type) would make the metric
name non-deterministic across different `Executor` implementations for
what is conceptually the same kind of event. Per-step metrics remain
an explicit Non-goal.

**Q14 — Does `execute_plan` capture step inputs/outputs in
metrics/traces?** No — not contested, matching `execute(module,
...)`'s existing behavior (it records only a duration, never the
module's actual input/output value) and this project's standing
"no automatic payload logging" security rule (see `execution.py`'s
own docstring: "may contain sensitive, handler-produced data this
module knows nothing about").

**Q15 — Are execution semantics protected from observability
failures?** **No — not protected, and this ADR states the exact
resulting contract explicitly rather than leaving it as an
undetermined "current behavior" to be discovered during
implementation.** The 15A/15B audit confirmed `execute(module, ...)`
today has no guard around `metrics.record`, `trace.start_span`, or
`log_event`. **Frozen during 15D adversarial review (see ADV-05)**,
the exact, deliberate policy for this version — for both the
pre-existing `execute(module, ...)` path and the new `execute_plan`
path — is:

> Observability failures are not isolated from execution outcome and
> may propagate independently of, or in place of, the primary
> execution result. If a handler/module succeeds but a subsequent
> `metrics.record`/`trace.start_span`/`log_event` call raises, that
> instrumentation exception propagates from `execute_plan`/`execute`
> instead of a successful return — the caller cannot distinguish this
> case from a component/handler failure by exception type alone. This
> is not a supported reliability guarantee in this version; a caller
> requiring one must not currently rely on `metrics.record`,
> `trace.start_span`, or `log_event` never raising.

This is a genuine architectural limitation, not a defect this ADR
introduces — it already exists in `execute(module, ...)` and this ADR
declines to fix it unilaterally as an unscoped side effect (see
"Alternatives considered"), since a real fix (e.g. wrapping
instrumentation calls to guarantee they cannot mask a
component/handler outcome) is a distinct concern that would need to
apply to both methods at once, informed by a real requirement, not
introduced quietly inside this ADR's narrower scope. OBS-01 and OBS-02
(see Testing strategy) pin this exact, named behavior with a test —
not an ambiguous "whatever happens" placeholder.

**Q16 — Sync or async?** Synchronous only, matching `Executor`'s
existing ADR-018 constraint exactly. No `async def` anywhere in this
ADR's contract.

**Q17 — Method name?** `execute_plan`, mirroring `execute`'s existing
naming (verb + noun) rather than `run_plan`, `plan_execute`, or a
separate class.

**Q18 — Does the engine retain the plan, handler, or executor after
the call?** No. `execute_plan` is stateless in exactly the same way
`execute(module, ...)` already is — `Run`/`Trace`/`MetricsCollector`
are created fresh per call and returned to the caller; no
`self.plan`/`self.handler`/`self.executor` attribute is set. The
`ExecutionEngine` instance itself (`self.level`) is unchanged and
remains reusable across both `execute` and `execute_plan` calls,
exactly as it already is reusable across repeated `execute` calls.

## 15D adversarial review findings

Applied to this revision, most severe first. Each is cross-referenced
to where the fix now lives.

1. **BLOCKER (ADV-01) — the root `ExecutionContext` `execute_plan`
   creates was unreachable by the handler, and the ADR's original
   wording ("a caller derives it themselves") implied a possibility
   that didn't actually exist for the zero-configuration case.**
   **Fix**: adopted explicit policy option A — `ExecutionContext`
   propagation into step work is entirely out of scope for this API;
   `execute_plan`'s context exists solely for engine-owned lifecycle
   identity. Stated explicitly, with the specific
   `engine.execute_plan(plan, handler)` failure-to-assume scenario
   spelled out, so a future reader cannot reasonably conclude
   otherwise — see Q2/Q6.
2. **BLOCKER (ADV-02) — the ADR claimed a future async executor could
   be substituted via the `executor` parameter, which ADR-018 already
   established is structurally impossible.** **Fix**: corrected to
   state `executor`-substitutability applies only to future
   *synchronous* `Executor` implementations; a future async engine
   entry point would need its own, separate contract — see Q12.
3. **MAJOR (ADV-03) — the plan-level span's name was unspecified.**
   **Fix**: frozen to the literal `"execute_plan"`, with no automatic
   attributes beyond what `execute(module, ...)`'s own span already
   carries — see Q7, TRACE-01.
4. **MAJOR (ADV-04) — the metric name was left as a vague
   `{engine-scoped name}.duration_s` placeholder.** **Fix**: frozen to
   the literal `"execution_plan.duration_s"`, distinct from and
   non-conflicting with `execute(module, ...)`'s existing
   `f"{module_name}.duration_s"` convention — see Q13, METRIC-01.
5. **MAJOR (ADV-05) — the observability-failure question was
   acknowledged as unresolved but not actually decided, leaving
   materially different possible failure contracts (instrumentation
   exception replacing a success, or replacing a handler failure)
   underspecified.** **Fix**: froze the exact policy — observability
   failures are not isolated and may propagate in place of the primary
   execution outcome, for both `execute` and `execute_plan`, stated as
   an explicit, tested (not merely documented) contract — see Q15,
   OBS-01/OBS-02.
6. **MINOR (ADV-06) — "empty plan succeeds" didn't specify what a full
   successful lifecycle actually requires**, risking an implementation
   that treats an empty plan as a no-op shortcut skipping
   `Run`/`Trace`/`Metrics`. **Fix**: PLAN-01 now asserts the complete
   lifecycle explicitly (`Run.status`, `output.values`, span count and
   name, metric count) — see Testing strategy.
7. **MINOR (ADV-07) — no single frozen sequence existed for
   success/failure ordering across `Run`/`Trace`/`Metrics`/`Executor`,
   making an implementation-order mistake likely.** **Fix**: added an
   exact lifecycle-sequence diagram mirroring `execute(module, ...)`'s
   existing structure precisely — see "Exact lifecycle sequence"
   below.

All seven findings are corrections to underspecified or incorrect
statements within the same overall design — none required rejecting
the additive `execute_plan` approach, the `Executor`-delegation
boundary, or the decision not to widen `StepHandler`. No second
adversarial round is required.

## Decision

### Naming and location: `ExecutionEngine.execute_plan`, `src/ragtorch/core/engine.py`

Added to the existing `engine.py`, not a new module — this is an
additive method on the existing `ExecutionEngine` class, not a new
runtime type. `execution.py` (ADR-018) remains untouched; `engine.py`
gains one new import (`ragtorch.core.execution_plan.ExecutionPlan` and
`ragtorch.core.execution.{Executor, SequentialExecutor, StepHandler}`)
and one new method.

### Public contract

```python
def execute_plan(
    self,
    plan: ExecutionPlan,
    handler: StepHandler,
    *,
    context: ExecutionContext | None = None,
    executor: Executor | None = None,
) -> ExecutionResult:
    """Run plan via executor (defaulting to SequentialExecutor(), any
    other *synchronous* Executor satisfying ADR-018's Protocol --
    never an async one, which cannot structurally satisfy it), under
    the same Run/Trace/Metrics lifecycle guarantee execute() already
    provides for a single Module call.

    Creates exactly one Run and, at DEBUG level, exactly one span
    named "execute_plan" for the whole call -- not one per step (see
    ADR-019 Q7/Q8, mirroring ADR-007's existing Sequential non-goal).
    Records one "execution_plan.duration_s" metric sample at BASIC or
    above.

    context, when supplied or defaulted, becomes Run.context ONLY --
    it is never passed to handler. StepHandler's signature (ADR-018)
    has no slot for an ExecutionContext, and this method makes no
    attempt to work around that; a caller needing per-step run
    identity inside handler's own work must construct and thread it
    themselves, entirely independently of this method's context
    parameter (see ADR-019 Q2).

    Delegates all plan iteration to executor -- never derives order or
    resolves ExecutionStep -> Component itself. Propagates the
    original, unwrapped exception on handler failure, after recording
    it on the Run, exactly as execute() already does for a Module
    failure. Observability failures (metrics.record/trace.start_span
    raising) are NOT isolated from this outcome and may propagate
    instead of it -- see ADR-019 Q15.
    """
```

`ExecutionResult` here is the engine's own existing return bundle
(`run`, `trace`, `metrics`, `output` property) — not
`StepExecutionResult` (ADR-018's `SequentialExecutor` return type).
`result.output` on the value returned by `execute_plan` is
`run.output`, which is set to whatever `Executor.execute` returned:
the `StepExecutionResult` for the whole plan. A caller who wants
individual step outputs reads `result.output.values`.

### Why `executor` defaults to `SequentialExecutor()`, not `None`-and-required

Matches `execute(module, ...)`'s zero-configuration default for the
common case, while still accepting an override — see Q12.

### Exact lifecycle sequence (frozen per ADV-07)

To make implementation order unambiguous, the success and failure
paths are frozen precisely — mirroring `execute(module, ...)`'s
existing structure exactly, substituting `Executor.execute(plan,
handler)` for `module(input, context=context)`:

```text
execute_plan(plan, handler, *, context=None, executor=None)
    |
    v
context = context or ExecutionContext()      # Q2: root context only,
    |                                         # not propagated to handler
    v
run = Run.start(context)
trace = Trace()
metrics = MetricsCollector()
executor = executor or SequentialExecutor()  # Q12
    |
    v
with optional span("execute_plan", run_id=context.run_id):  # Q7, DEBUG only
    try:
        step_result = executor.execute(plan, handler)  # StepExecutionResult
    except Exception as exc:
        run.fail(exc)                        # Q9
        record "execution_plan.duration_s"   # Q13 -- same point as success path
        bare raise                           # Q9: no wrapping, original object
    |
    v  (success only)
run.succeed(step_result)
record "execution_plan.duration_s"
return ExecutionResult(run=run, trace=trace, metrics=metrics)
```

Per Q15/ADV-05, this sequence does **not** guard `run.fail`,
`metrics.record`, or the span context manager against raising
themselves — if any of those raise, that exception propagates instead
of (on the failure path) the handler's original exception, or instead
of (on the success path) a normal return. This is the exact,
frozen consequence of Q15's policy, not a separate decision.

### Why no per-step `ExecutionContext` injection

See Q2 above — the single most consequential decision in this ADR,
made explicit rather than assumed, per the project owner's correction
during drafting.

### Why observability-failure protection is explicitly deferred, not fixed

See Q15 above for the exact, frozen policy statement. Fixing
`execute(module, ...)`'s pre-existing gap is out of this ADR's scope;
silently fixing it only for the new `execute_plan` path would create
two different reliability guarantees for the "same" concern
(engine-owned observability) depending on which method a caller used —
inconsistent, not merely incomplete. This ADR instead locks the actual
existing behavior with a named policy statement and OBS-01/OBS-02
tests, so a future reader finds a documented, tested contract rather
than an implicit gap to rediscover.

## Non-goals

Explicitly deferred, not part of this decision:

- **Any change to `execute(module, ...)`.** Zero lines touched in its
  existing implementation, signature, or tests.
- **Per-step spans or per-step metrics.** See Q7/Q8/Q13.
- **Injecting `ExecutionContext` into `StepHandler`.** See Q2/Q5 — a
  breaking change to ADR-018's already-Accepted contract, not
  attempted here.
- **Observability-failure isolation (fail-safe metrics/tracing).** See
  Q15 — a real, audit-confirmed gap this ADR names but does not fix,
  since it predates this ADR and also affects `execute(module, ...)`.
- **Async, parallel, or distributed plan execution.** `execute_plan`
  is synchronous only, matching `Executor`'s existing constraint.
- **Retries, timeouts, or any other invocation policy.**
- **Plan derivation or step-to-`Component` resolution inside the
  engine.** Stays entirely `Executor`'s and the handler's
  responsibility, per ADR-018.
- **A new `Executor` implementation.** `SequentialExecutor` remains the
  only one; `execute_plan`'s `executor` parameter exists so a future
  one can be substituted without engine changes, not so this ADR
  builds one.

## Alternatives considered

- **Overload `execute` to accept either a `Module` or an
  `ExecutionPlan`.** Rejected — see Q1. Couples two unrelated call
  shapes into one signature for no benefit.
- **Widen `StepHandler` to `__call__(step, context, execution_context)`.**
  Rejected — see Q2/Q5. Breaks ADR-018's already-Accepted public
  contract; this ADR has no standing to make that change unilaterally,
  and no evidence from the audit that it's actually needed rather than
  merely convenient.
- **Use a thread-local or mutable-attribute side channel so a handler
  can read the "current" per-step `ExecutionContext` without a
  signature change.** Rejected — see Q2. Reintroduces exactly the kind
  of global mutable execution state `ExecutionContext` (ADR-002) was
  designed to avoid; no precedent for this pattern exists anywhere
  else in this codebase.
- **Hard-code `SequentialExecutor` inside `execute_plan` with no
  override.** Rejected — see Q12. Would force a future alternate
  `Executor` to require engine changes.
- **Fix the observability-failure gap as part of this ADR, since it
  was found during this ADR's own audit.** Rejected — see Q15. The gap
  predates this ADR, applies equally to `execute(module, ...)`, and
  fixing it only for the new path would create an inconsistent
  reliability guarantee between the two methods. Named explicitly as a
  known limitation instead; fixing it (for both paths at once) is
  future work.
- **Derive the span name or metric name from the executor's type or
  the plan (e.g. `f"{type(executor).__name__}.duration_s"`).**
  Rejected — see ADV-03/ADV-04, Q7/Q13. Would make the metric/span
  name non-deterministic across different `Executor` implementations
  for what is conceptually the same kind of event, and would be a
  worse observability contract than one fixed, predictable name a
  dashboard or alert can match on permanently.
- **Require `context` always be caller-supplied, so the caller at
  least holds a reference to use when building `handler`.** Rejected
  — see Q2. Does not actually solve the handler-reachability problem
  (a handler built before the call still cannot receive the engine's
  per-call context automatically), and removes the zero-configuration
  default `execute(module, ...)` already provides.

## Security

`execute_plan` introduces no new trust boundary beyond what `execute`
already establishes — handler/component invocation is trusted
application code. No automatic logging of `StepExecutionContext.results`,
`StepExecutionResult.values`, or `run.output` — those may contain
sensitive, handler-produced data this method knows nothing about,
matching `execute(module, ...)`'s existing behavior (it never logs the
module's actual input/output either) and `execution.py`'s own
documented rule.

## Dependency review

Zero new runtime dependencies. `engine.py` gains imports from
`ragtorch.core.execution_plan` (`ExecutionPlan`) and
`ragtorch.core.execution` (`Executor`, `SequentialExecutor`,
`StepHandler`) — both already-existing internal modules, no new
package.

## Compatibility

`execute(module, ...)`, `Run`, `Trace`, `MetricsCollector`,
`ExecutionContext`, `Executor`, `SequentialExecutor`, `StepHandler`,
`StepExecutionContext`, `StepExecutionResult`, `ExecutionPlan`,
`ExecutionStep`, `Sequential`, `Component`, `CompositionGraph` — all
unchanged. `execute_plan` and its parameter types are a pure addition
to the existing `ExecutionEngine` class. No new public type is
introduced by this ADR — `execute_plan` reuses `ExecutionEngine`'s
existing `ExecutionResult`, `ragtorch.core.context.ExecutionContext`,
and ADR-018's `Executor`/`StepHandler`/`ExecutionPlan` types directly.

## Testing strategy

- **PLAN-01** Empty plan (`ExecutionPlan(steps=())`) succeeds, asserted
  as a complete lifecycle, not merely "no error" (frozen during 15D
  adversarial review — see ADV-06, to prevent an empty plan being
  treated as a special no-op path that skips lifecycle
  instrumentation): `run.status == RunStatus.SUCCEEDED`;
  `result.output` is a `StepExecutionResult` with `values == {}`; at
  `DEBUG` level, exactly one span exists (`len(result.trace.spans) ==
  1`), named `"execute_plan"`; at `BASIC` level or above, exactly one
  `"execution_plan.duration_s"` metric sample is recorded; `handler`
  is never called.
- **PLAN-02** Steps execute in `plan.steps` order (verified via a
  recording handler, reusing the same pattern as ADR-018's EXEC-04).
- **PLAN-03** A test-double `Executor` (not `SequentialExecutor`) can
  be substituted via the `executor` parameter and is actually used
  (verified via a call-recording fake), proving `execute_plan`
  delegates rather than hard-coding.
- **CTX-01** A caller-supplied root `ExecutionContext` is preserved as
  `run.context` — identity-checked (`result.run.context is context`),
  not merely equality-checked.
- **CTX-02** No caller-supplied context: `execute_plan` still creates
  a default `ExecutionContext`, matching `execute(module, ...)`'s
  existing "no context supplied" behavior (`test_engine_without_
  explicit_context_still_creates_one_and_propagates_it`'s equivalent
  for plans).
- **CTX-03** The handler never receives an `ExecutionContext` — a
  handler whose signature only accepts `(step, StepExecutionContext)`
  (the ADR-018 contract exactly) runs successfully with no
  `TypeError`/missing-argument error, proving `execute_plan` calls
  `handler(step, step_context)` with no additional positional or
  keyword argument (frozen per ADV-01, Q2 — a direct regression guard
  against ever silently widening the call).
- **TRACE-01** At `DEBUG` level, exactly one span exists after a
  successful multi-step plan execution (`len(result.trace.spans) ==
  1`), mirroring `test_engine_full_rag_shaped_pipeline`, **and its
  name is exactly `"execute_plan"`** (frozen per ADV-03 — asserted
  exactly, not merely that a span exists).
- **TRACE-02** No per-step spans exist — explicit negative assertion,
  not merely "exactly one," to guard against a future accidental
  per-step span addition going unnoticed.
- **METRIC-01** Exactly one duration metric sample is recorded under
  the exact name `"execution_plan.duration_s"` (frozen per ADV-04) for
  a successful plan execution at `BASIC` level or above; none at
  `OFF`.
- **FAIL-01** A handler failure mid-plan marks `run.status ==
  RunStatus.FAILED` and sets `run.error`.
- **FAIL-02** The exact original exception object propagates out of
  `execute_plan` unchanged (`exc_info.value is error`), reusing
  ADR-018's own FAIL-02 pattern one layer up.
- **FAIL-03** Steps after the failing one are never called (recording
  handler, reusing ADR-018's FAIL-03 pattern).
- **FAIL-04** No `ExecutionResult` is returned or accessible after a
  failure — the only observable outcome is the propagated exception.
- **COMPAT-01** `execute(module, ...)`'s existing behavior and full
  existing test suite (`test_engine.py`, `test_nested_execution.py`,
  `test_execution_lifecycle.py`, `test_engine_execution.py`) pass
  unmodified.
- **COMPAT-02** `Sequential`'s existing behavior and tests
  (`test_sequential.py`, `test_sequential_context.py`) pass unmodified.
- **COMPAT-03** `ExecutionPlan`/`ExecutionStep`/`plan()`'s existing
  behavior and tests pass unmodified.
- **OBS-01** When `MetricsCollector.record` raises during
  `execute_plan` (e.g. a fake `MetricsCollector` that raises on
  `record`), the resulting exception propagates from `execute_plan`
  and the caller cannot recover a successful `ExecutionResult` for
  that call — pinning the exact policy frozen in Q15 (per ADV-05),
  not an open-ended "whatever happens" placeholder.
- **OBS-02** Same for `Trace.start_span`/span-context failure — a
  fake `Trace` whose `start_span` raises causes that exception to
  propagate from `execute_plan`, pinning the same Q15 policy.
- **SEC-01** No automatic logging of `StepExecutionContext.results`,
  `StepExecutionResult.values`, or `run.output` (source-inspection or
  behavioral test, reusing the established pattern).
- **API-01** `execute_plan`'s parameter/return types
  (`ExecutionPlan`, `StepHandler`, `Executor`, `ExecutionContext`,
  `ExecutionResult`) introduce no new bare-name collision in
  `ragtorch.core.__all__`/`ragtorch.__all__` — verified by the
  existing public API parity test, unmodified in membership by this
  ADR (no new type is exported — see Compatibility).
- **STATE-01** The same `ExecutionEngine` instance can call
  `execute_plan` and `execute` repeatedly, in any order, without one
  call's `Run`/`Trace`/`Metrics` leaking into another's — reusing
  ADR-018's STATE-01/STATE-02 pattern at the engine layer.

## Benchmark strategy

Per ADR-009, `benchmarks/step15_plan_execution_runtime.py`. Isolates
**runtime overhead**, not `SequentialExecutor`'s already-benchmarked
snapshot-copying cost (ADR-018) — measures a baseline
(`SequentialExecutor().execute(plan, handler)` directly) against
`ExecutionEngine().execute_plan(plan, handler)` at 10/100/1,000 steps
only (not 10,000/100,000 — ADR-018's benchmark already established
that cost curve; this benchmark's purpose is the *additional* overhead
`Run`/`Trace`/`Metrics` creation adds on top of it, which would be
swamped by the O(n²) term at larger sizes and uninformative there).
Reports total time and per-step overhead for both `BASIC` and `DEBUG`
observability levels. As with every prior benchmark in this project:
measures, does not prove, an overhead claim; no threshold assertion,
not wired into CI (matching Steps 13/14's precedent).

## Consequences

- A caller with an `ExecutionPlan` and a `StepHandler` gets the same
  `Run`/`Trace`/`Metrics` lifecycle guarantee `execute(module, ...)`
  already gives a single `Module` call, without the engine becoming a
  second planner or executor.
- `StepHandler`'s ADR-018 contract stays exactly as accepted — no
  breaking change, no implicit context side-channel. A caller needing
  per-step run identity inside their handler derives it themselves,
  following the same `context.child(...)` pattern `Sequential`
  already established one layer down.
- The audit-confirmed absence of observability-failure isolation in
  `execute(module, ...)` is named and tested (OBS-01/OBS-02) rather
  than silently inherited or silently "fixed" as an unscoped side
  effect of this ADR — a future ADR can address it for both paths at
  once if ever justified.
- `ExecutionEngine` remains swappable in principle: it depends on
  `Executor`/`ExecutionPlan`, never the reverse, and `execute_plan`'s
  `executor` parameter keeps a future *synchronous* alternative (e.g.
  `ParallelExecutor`) usable without engine changes — corrected during
  15D review (ADV-02) to no longer imply this extends to a future
  async executor, which cannot satisfy `Executor` at all (ADR-018) and
  would need its own separate async contract.
- Span name (`"execute_plan"`) and metric name
  (`"execution_plan.duration_s"`) are frozen, exact literals rather
  than vague placeholders — corrected during 15D review (ADV-03/ADV-04)
  specifically so a dashboard or alert built against this API has a
  stable name to depend on from the start.
- The audit-confirmed absence of observability-failure isolation in
  `execute(module, ...)` is named, frozen as an exact policy statement,
  and tested (OBS-01/OBS-02) rather than silently inherited, silently
  "fixed," or left as an ambiguous "current behavior" to be discovered
  during implementation — corrected during 15D review (ADV-05). A
  future ADR can address it for both paths at once if ever justified.
- Scope stays deliberately narrow: no per-step spans/metrics, no
  context-injection mechanism, no observability-failure fix, no async
  — consistent with every prior step's discipline.
