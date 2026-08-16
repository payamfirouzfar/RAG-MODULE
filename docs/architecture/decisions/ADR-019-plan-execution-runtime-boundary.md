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
`ExecutionContext`?** **It does not.** `StepHandler.__call__(step,
context: StepExecutionContext) -> object` (ADR-018) is already
Accepted, frozen public API, with no parameter for `ExecutionContext`
at all. `execute_plan` creates exactly one root `ExecutionContext`
(via `Run.start(context)`, same as `execute(module, ...)`) for the
whole plan-level call, and does **not** derive or inject a per-step
child `ExecutionContext` into the handler. Rejected, explicitly, after
identifying that no non-speculative mechanism exists to do so without
either (a) widening `StepHandler`'s signature — a breaking change to
an already-Accepted contract this ADR has no standing to make
unilaterally — or (b) an implicit side-channel (thread-local, mutable
attribute) for context propagation, which this project has never used
elsewhere and which would introduce exactly the kind of "global
mutable execution state" `ExecutionContext` was originally designed to
avoid (see `context.py`'s own docstring: "without relying on
process-wide global state"). If a caller's handler needs per-step run
identity (e.g. because it internally invokes a `Component`), the
caller derives that themselves when constructing the handler — for
example, by closing over `context.child(node_id=...)` per call inside
their own handler function, exactly as `Sequential.forward` already
does one layer down for nested `Module` calls
(`context.child(step=f"step{i}")`). This ADR provides the root
`ExecutionContext` a caller needs to do that; it does not do it for
them.

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
engine doesn't create one?** Nothing, in this ADR. `Sequential`'s
`context.child(step=f"step{i}")` precedent remains real and directly
informs how a *caller* might build a context-aware handler, but
`execute_plan` itself does not replicate that derivation — see Q2.

**Q7 — How many spans does `execute_plan` create?** Exactly one for
the whole plan-level call, at `DEBUG` observability level — mirroring
`execute(module, ...)`'s existing behavior exactly, and consistent
with ADR-007's already-tested non-goal for `Sequential`
(`test_engine_full_rag_shaped_pipeline` asserts
`len(result.trace.spans) == 1` even for a 3-stage nested pipeline).
Per-step spans are an explicit Non-goal — not silently foreclosed, but
not something this ADR's audit found evidence justifying, and adding
them would reopen ADR-007's settled non-goal without new justification.

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
an `Executor | None`. Rejected: hard-coding `SequentialExecutor`
internally with no override, which would make a future
`AsyncExecutor`/`ParallelExecutor` require engine changes to use —
exactly the coupling ADR-018's `Executor` `Protocol` exists to avoid.
Rejected: requiring the caller to always supply one, which would make
the common case (`SequentialExecutor`, the only implementation that
currently exists) more verbose than `execute(module, ...)`'s
zero-configuration default.

**Q13 — What does `execute_plan` measure?** One plan-level duration
metric (`{engine-scoped name}.duration_s`), matching
`execute(module, ...)`'s existing per-module convention exactly — not
one metric per step. Per-step metrics are an explicit Non-goal.

**Q14 — Does `execute_plan` capture step inputs/outputs in
metrics/traces?** No — not contested, matching `execute(module,
...)`'s existing behavior (it records only a duration, never the
module's actual input/output value) and this project's standing
"no automatic payload logging" security rule (see `execution.py`'s
own docstring: "may contain sensitive, handler-produced data this
module knows nothing about").

**Q15 — Are execution semantics protected from observability
failures?** **Not in this version — and this is stated explicitly,
not silently inherited.** The 15A/15B audit confirmed `execute(module,
...)` today has no guard around `metrics.record`, `trace.start_span`,
or `log_event` — if instrumentation itself raised, it would currently
propagate and corrupt the caller's view of what actually failed
(component vs. observability). `execute_plan` inherits this same,
already-existing gap rather than fixing it unilaterally as a side
effect of this ADR — fixing it is a distinct concern that would also
apply to `execute(module, ...)`, which this ADR does not touch. OBS-01
and OBS-02 (see Testing strategy) exist specifically to make this gap
visible and tested, not silently assumed away, and the evaluation
report names it as a known limitation shared with the pre-existing
`execute(module, ...)` path.

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
    """Run plan via executor (defaulting to SequentialExecutor()),
    under the same Run/Trace/Metrics lifecycle guarantee execute()
    already provides for a single Module call.

    Creates exactly one Run and, at DEBUG level, exactly one span for
    the whole call -- not one per step (see ADR-019 Q7/Q8, mirroring
    ADR-007's existing Sequential non-goal). Does not inject a
    per-step ExecutionContext into handler: StepHandler's signature
    (ADR-018) has no slot for one; a caller that needs per-step run
    identity derives it themselves when building handler (see ADR-019
    Q2). Delegates all plan iteration to executor -- never derives
    order or resolves ExecutionStep -> Component itself. Propagates
    the original, unwrapped exception on handler failure, after
    recording it on the Run, exactly as execute() already does for a
    Module failure.
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

### Why no per-step `ExecutionContext` injection

See Q2 above — the single most consequential decision in this ADR,
made explicit rather than assumed, per the project owner's correction
during drafting.

### Why observability-failure protection is explicitly deferred, not fixed

See Q15 above. Fixing `execute(module, ...)`'s pre-existing gap is out
of this ADR's scope; silently fixing it only for the new `execute_plan`
path would create two different reliability guarantees for the "same"
concern (engine-owned observability) depending on which method a
caller used — inconsistent, not merely incomplete.

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

- **PLAN-01** Empty plan (`ExecutionPlan(steps=())`) succeeds:
  `execute_plan` returns an `ExecutionResult` with `run.status ==
  SUCCEEDED` and `result.output.values == {}`, without calling
  `handler`.
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
- **TRACE-01** At `DEBUG` level, exactly one span exists after a
  successful multi-step plan execution (`len(result.trace.spans) ==
  1`), mirroring `test_engine_full_rag_shaped_pipeline`.
- **TRACE-02** No per-step spans exist — explicit negative assertion,
  not merely "exactly one," to guard against a future accidental
  per-step span addition going unnoticed.
- **METRIC-01** Exactly one duration metric is recorded for a
  successful plan execution at `BASIC` level or above; none at `OFF`.
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
- **OBS-01** Explicit test defining current behavior when
  `MetricsCollector.record` raises during `execute_plan` — documents,
  rather than silently allows, whatever the actual (unguarded)
  behavior is, per Q15.
- **OBS-02** Same for `Trace.start_span`/span-context failure.
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
  `executor` parameter keeps a future `AsyncExecutor`/`ParallelExecutor`
  usable without engine changes.
- Scope stays deliberately narrow: no per-step spans/metrics, no
  context-injection mechanism, no observability-failure fix, no async
  — consistent with every prior step's discipline.
