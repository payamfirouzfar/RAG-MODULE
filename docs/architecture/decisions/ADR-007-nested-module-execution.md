# ADR-007: Nested Module Execution

## Context

`ExecutionEngine` (Step 3, ADR-006) executes exactly one top-level `Module`
call and records `Run`/`Trace`/`Metrics` for it. When that module is a
composite — `Sequential`, or any future `Module` whose `forward()` calls
child modules — those children are invoked as plain `child(value)` calls
with no `ExecutionContext` at all. ADR-006 explicitly deferred this:

> Context propagation to children is the composite's responsibility, not
> the engine's... This ADR commits only to: the engine does not silently
> drop or mutate the context it's given.

That gap is now a real limitation. A future `RAGModule` composed of
`Retriever`, `Reranker`, `Generator` children has no formally defined way
for those children to know they're part of a larger execution, no way to
derive a child identity from the parent's `run_id`, and no guarantee that
one child's execution can't leak state into a sibling's. Every future
composite would otherwise invent its own answer to this question.

## Decision

### What Step 4 delivers

`ExecutionContext` propagation through composite `Module` execution,
implemented as an explicit, opt-in parameter — nothing else. Specifically:

1. `Module.__call__` gains an optional keyword-only parameter:
   `__call__(self, input, *, context: ExecutionContext | None = None)`.
2. `Module.__call__` inspects (once per class, cached) whether the
   subclass's `forward()` accepts a `context` parameter. If it does,
   `context` is passed through: `self.forward(input, context=context)`.
   If not, `forward(input)` is called exactly as before.
3. `Sequential.forward(self, input, *, context=None)` derives a child
   context per step — `context.child(step=name)` when a context is
   given — and passes it to each step's `__call__`. When no context is
   given (e.g. `pipeline("hello")` called directly, without an engine),
   `Sequential` runs exactly as it did before this ADR: no context is
   created or threaded anywhere.

### Invariants

- **I1. Backward compatibility.** `module(input)` — no context — remains
  valid and behaves identically to pre-Step-4 code. Every Step 1-3 test
  passes unmodified.
- **I2. No global execution context.** Context is passed explicitly
  through call arguments only. No thread-local, no contextvar, no module-
  level "current context." Consistent with ADR-002.
- **I3. Parent execution identity is preserved.** A child's context
  carries `parent_run_id` pointing at the parent's `run_id`, via the
  existing `ExecutionContext.child()` (built in Step 2, unchanged here).
- **I4. Explicit derived context per child.** A composite passes each
  child a distinct `context.child(...)` — never the same context object
  it received, and never a mutated copy of it (`ExecutionContext` is
  already frozen, so mutation is structurally impossible, only replacement).
- **I5. Failures propagate normally.** A child's exception propagates
  through the parent exactly as it does today (`Module.__call__` already
  wraps it in `ExecutionError`; that is unchanged by this ADR). Sibling
  modules after a failed one do not execute — this falls out of
  `Sequential.forward`'s existing sequential loop and is not new behavior,
  just newly verified under context propagation.
- **I6. Observability must not silently disappear.** A context-aware
  composite executed *with* a context still produces a valid `Run` via
  the engine exactly as before; nothing about context propagation may
  cause the engine's existing BASIC/DEBUG guarantees to stop holding for
  the top-level call.
- **I7. Signature detection has bounded, cached cost.** Whether a
  subclass's `forward` accepts `context` is determined once per class
  (via `inspect.signature`, cached on the class, not the instance) rather
  than re-inspected on every call.

### Non-goals (explicitly out of scope for Step 4)

- **Automatic nested trace spans / per-child metrics.** Making
  `Sequential`'s children each appear as spans in the parent's `Trace`, or
  each get their own duration metric, requires deciding how `Trace`/
  `MetricsCollector` — not just `ExecutionContext` — reach a composite's
  children, which is a separable design question deserving its own step
  once context propagation itself is proven. Today, a module executed
  through the engine still gets exactly one span (the top-level call), as
  it did before this ADR.
- **DAG scheduling, parallel/concurrent execution, distributed execution.**
  Nested execution here means synchronous, in-process, depth-first calls —
  the same execution model `Sequential` already has.
- **Retry policy, caching.** Not addressed by context propagation.
- **Persistent run artifacts.** Still deferred per ADR-006.
- **A general graph/composition engine.** `Sequential` is the only
  composite touched in this step; a generic `ModuleList`/`ModuleDict`/
  graph composition API is future work (see the updated roadmap).

### Why signature detection instead of a required parameter or a separate base class

A required `context` parameter on every `forward()` would break every
existing `Module` subclass (I1 violation). A separate
`ContextAwareModule` base class would work without breaking anything, but
splits "the module contract" into two incompatible shapes users must
choose between up front — directly against ADR-001's "the interface
should be small... a good interface is difficult to misunderstand."
Detecting whether `forward` opts in via its own signature keeps exactly
one `Module` contract: subclasses that don't care about context are
unaffected byte-for-byte; subclasses that do, add one parameter.

### Why `Sequential` derives `context.child()` per step rather than reusing one context

Reusing the parent's context for every step would mean two different
child executions (e.g. step 0 and step 1) report the same `run_id`,
making it impossible to later distinguish "the retriever's run" from "the
reranker's run" in any log or artifact keyed by `run_id`. `child()` (built
in Step 2) already exists precisely to prevent this — Step 4 is its first
real consumer.

## Alternatives considered

- **Instance-attribute context (`self._context = context` before calling
  `forward`).** Rejected: a `Module` instance called reentrantly — from
  two concurrent top-level executions, or recursively — would have one
  execution's context clobbered by the other's, exactly the hazard
  ADR-002 ruled out for the engine-level design. Explicit parameter
  passing has no such hazard because each call's context lives on that
  call's stack frame, not on the shared instance.
- **contextvars-based implicit propagation.** Rejected for the same
  reason as ADR-002's original global-state rejection: it would make
  context propagation *look* automatic while actually depending on
  Python's contextvar-copying semantics being correct across every future
  execution model (threads, asyncio tasks, generators) — a much larger
  surface to get right than "pass the argument." May be revisited as
  optional sugar once the explicit primitive is proven, not before.

## Consequences

- A future `RAGModule` with `Retriever`/`Reranker`/`Generator` children
  can give each child a distinct, correctly-parented `ExecutionContext`
  today, without waiting for a full graph engine.
- `Module`'s public contract grows by exactly one optional parameter;
  nothing published in Steps 1-3 changes behavior for callers who ignore
  it.
- The deferred non-goals (nested tracing, DAG execution) have a concrete
  foundation to build on: `ExecutionContext` propagation, not something
  they need to invent themselves.
