# ADR-022: Execution-Scoped Event Delivery

## Status

Accepted

Accepted after real GitHub Actions post-merge CI confirmed on the
actual merged `main` SHA — not from PR CI or local checks alone, per
this project's standing rule that "PR green is not proof." Evidence
trail:

- PR #25 (18A-18K: audit, ADR, contract, implementation, unit/
  integration/failure/concurrency tests, benchmark, evaluation,
  expanded compatibility/security/dependency review): merged
  `e83d23a`, post-merge CI run
  [32038947496](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32038947496),
  461/461 on 3.10/3.11/3.12, lint clean, on commit `e83d23a`.

## Context

`EventBus` (`ragtorch.core.events`, ADR-003) is a single, process-wide
global instance (`_bus = EventBus()`, `src/ragtorch/core/module.py:25`),
shared by every `Module.__call__` invocation in the process with no
per-execution isolation. Requirement A5: *"Explicit execution identity
| ExecutionContext + execution-scoped Events | **EventBus must
eventually become execution-scoped for isolation**."* Requirement A10:
*"No global mutable execution state | ... | **process-wide EventBus
remains as compatibility delivery mechanism**."* Both have stood open
since Step 4. `docs/architecture/v0.1-architecture.md` §5 requires
every nested execution to preserve "root run identity; parent-child
relationship; immutable metadata; **sibling isolation**."

Grounded in direct inspection (18A/18B audit) of `context.py`,
`run.py`, `events.py`, `module.py`, `engine.py` (full files) and
`sequential.py`/`block.py`/`execution.py`/`execution_plan.py` (grepped,
confirmed to contain zero event references) — not assumed from memory.
Three findings from that audit directly shape this decision:

1. **Identity already satisfies §5's first three invariants; only
   delivery does not.** Verified by direct construction — not
   asserted — with `Sequential(A(), B())` under one root
   `ExecutionContext`: `A`/`B` receive distinct `run_id`s, both
   correctly parented to `Sequential`'s `run_id`. A single subscribed
   listener, however, receives all six lifecycle events from the whole
   tree, interleaved, with no mechanism to observe only one execution.
2. **`Event`/`EventBus`, `Run`, and `ExecutionEngine`'s structured
   `log_event` logging are three entirely disjoint signal channels
   today** — `Run` is created only by `ExecutionEngine.execute`/
   `execute_plan`, never by a bare `Module.__call__` call (confirmed:
   `Run.start` appears only in `engine.py`); a bare `module(input,
   context=ctx)` call with no engine involved publishes events but has
   no `Run` at all. This ADR scopes **event delivery only** — it does
   not scope `Run`, `Trace`, `MetricsCollector`, or `log_event`
   logging, none of which this ADR touches.
3. **`event_bus()`'s current, tested semantics must not be silently
   redefined.** `tests/unit/core/test_events.py`'s existing, passing
   tests (`test_module_call_emits_started_and_finished_events`,
   `test_nested_context_events_remain_distinguishable`) rely on
   `event_bus()` returning one bus that sees *everything*, with
   listeners filtering manually by `run_id`/`module_name`. Any design
   that makes `event_bus()`'s return value depend on "current
   execution" would break both tests and would also conflict with
   architecture doc §5's explicit "no implicit current execution...
   is introduced" constraint.

**This ADR does not fix the pre-existing, audit-confirmed gaps in
listener-failure isolation (a raising listener crashes `publish()`
indistinguishably from a real execution failure) or concurrency-safety
of `EventBus._listeners` (unsynchronized list mutation)** — both are
real, but unrelated to *scoping*, and fixing them here would violate
this project's "one primitive per step" discipline (established
explicitly in Steps 6-9, reused for every step since). Both are named
as explicit, deferred future work.

```text
ExecutionContext (frozen, immutable identity + metadata)
      |
      +-- run_id, parent_run_id, metadata (unchanged, ADR-002)
      +-- event_scope: EventScope | None = None (this ADR, additive)
                |
                v
      EventScope (new type, this ADR)
                |
                +-- owns its own listener list, entirely separate
                |   from the existing global _bus
                +-- .child() propagates the SAME EventScope instance
                    unchanged -- a child execution's events are
                    visible to whatever observed its parent, exactly
                    as today's global bus already lets a listener see
                    a whole Sequential's nested calls; what's new is
                    that an UNRELATED execution's separate EventScope
                    receives nothing from this one

Module.__call__(input, context=ctx)
      |
      +-- ctx is None:
      |       -> global EventBus only, run_id=None, no EventScope
      +-- ctx is not None, ctx.event_scope is None:
      |       -> global EventBus only
      +-- ctx is not None, ctx.event_scope is scope:
              -> global EventBus
              -> scope
              (both configured destinations receive the event under
              normal listener execution; see "Failure semantics and
              delivery ordering" below -- this is not an atomic
              broadcast)
```

## Problem

We need a minimal, additive mechanism for a caller to observe only
their own execution's events (and its nested children's), without (a)
changing `event_bus()`'s existing, tested global-delivery semantics in
any way, (b) introducing implicit ambient/thread-local execution state
that architecture doc §5 explicitly prohibits, (c) conflating event
delivery scoping with `Run`/`Trace`/`Metrics`/logging scoping, which
are today entirely separate systems this ADR does not touch, and (d)
opportunistically fixing the unrelated listener-failure and
concurrency-safety gaps the audit found but did not attribute to this
requirement.

## Open questions this ADR must decide before any code is written

**Q1 — What exactly is being scoped?** Event delivery only.
`Run`/`Trace`/`MetricsCollector` (owned by `ExecutionEngine`) and
`log_event` structured logging remain entirely unmodified and
unscoped by this ADR — see Finding 2. An "execution-scoped delivery
scope" is not synonymous with an `ExecutionEngine` `Run`; a bare
`Module.__call__` call with a scoped `ExecutionContext` but no
`ExecutionEngine` still gets scoped event delivery, since scoping
lives on `ExecutionContext`, not on `Run`.

**Q2 — What happens to the existing global `event_bus()`?**
Unchanged, exactly. `event_bus()` continues to return the same
process-wide `EventBus` singleton it always has;
`Module.__call__`'s existing, unconditional publish to that global bus
is not removed, gated, or made conditional on anything. **Confirmed
during 18C drafting**: this preserves both existing tests
(`test_module_call_emits_started_and_finished_events`,
`test_nested_context_events_remain_distinguishable`) byte-for-byte,
verified by re-reading their assertions against this decision before
freezing it. Rejected: making `event_bus()` return "the current
execution's scope" — breaks both tests and reintroduces exactly the
kind of implicit current-execution state architecture doc §5
prohibits.

**Q3 — What is the new scoping mechanism, concretely?**
`ExecutionContext` gains a new, optional field:
`event_scope: EventScope | None = None`. A caller who wants isolated
delivery constructs an `EventScope`, subscribes listeners to it, and
passes it into an `ExecutionContext`
(`ExecutionContext(event_scope=my_scope)`). `Module.__call__`
publishes each event to the global bus (Q2, unchanged) **and**, if
`context is not None and context.event_scope is not None`, also
publishes the same `Event` object to `context.event_scope`. Rejected:
a second explicit parameter threaded independently of
`ExecutionContext` (e.g. `Module.__call__(input, context=ctx,
event_scope=scope)`) — would require every existing call site that
threads `context` (`Sequential.forward`, `Block.forward`,
`_GraphBackedRAGModule.forward`, `ExecutionEngine.execute`/
`execute_plan`) to also thread a second, parallel parameter, doubling
the propagation surface for no benefit `ExecutionContext` doesn't
already provide — `ExecutionContext` already exists precisely to
carry per-execution identity and metadata (ADR-002); scope is an
additional piece of the same "this execution" concept, not an
unrelated one.

**Q4 — Does `ExecutionContext.child()` propagate `event_scope`?** Yes
— unchanged, the same `EventScope` instance the parent had. Verified
against the audit's own empirical `Sequential(A(), B())` construction:
today, one listener on the global bus already sees the whole nested
tree's events (that's how `test_nested_context_events_remain_distinguishable`
works). The new scoped mechanism preserves that same "a listener
subscribed to an execution sees its whole subtree" property — what's
new is that an *unrelated* execution's `EventScope` (from a different
root `ExecutionContext`, not derived via `.child()` from this one)
receives nothing from this one. Rejected: giving each `.child()` call
a fresh, unrelated `EventScope` — would mean a caller who scopes their
top-level execution and expects to observe everything underneath it
(the exact "sibling isolation between *unrelated* executions, not
between parent and child" reading of architecture doc §5) would
silently stop seeing nested events, a surprising and untested
regression from today's actual behavior.

**Q5 — Is `EventScope` itself immutable?** No — like `EventBus`, it
owns mutable subscription state (`subscribe`/`unsubscribe`/`publish`),
matching the existing, established shape of `EventBus` exactly (see
Decision). `ExecutionContext` remains `frozen=True`; only the
*reference* to an `EventScope` is part of its frozen field set, not
the `EventScope`'s own internal listener list — consistent with how
`ExecutionContext.metadata` is already a `Mapping` (potentially
containing mutable values) inside an otherwise-frozen dataclass.

**Q6 — What happens with no context, or a context with no
`event_scope`?** Identical to today's existing behavior in both cases
— confirmed as an explicit, tested invariant, not an assumption.
`context is None`: the existing context-free `Module.__call__` branch
is entirely untouched, publishes only to the global bus, `run_id=None`,
exactly as `test_module_call_emits_started_and_finished_events`
already asserts. `context is not None` but `context.event_scope is
None` (the default): publishes only to the global bus, exactly as
every existing context-aware test already asserts — this is the
*default* for every `ExecutionContext` constructed without explicitly
supplying `event_scope`, so **all existing callers, with zero code
changes, get identical behavior to before this ADR**.

**Q7 — Does `EventScope` require a new class, or can `EventBus` itself
be reused?** A new class, `EventScope`, structurally identical to
`EventBus` (same `subscribe`/`unsubscribe`/`publish` shape) but a
distinct type. Rejected: reusing `EventBus` directly as the
per-context scope type — while structurally sufficient, naming the
new field's type `EventBus` would blur the conceptual distinction
between "the one process-wide compatibility bus" (existing,
`event_bus()`) and "this specific execution's delivery scope" (new,
`ExecutionContext.event_scope`) — the same "distinct name for a
distinct role" reasoning this project already applied for
`StepExecutionContext`/`StepExecutionResult` (ADR-018/020, avoiding
collision with `ExecutionContext`/`ExecutionResult`) and for keeping
`Block`/`RAGModule` as separate concepts despite structural overlap
with `Component`.

**Q8 — Does scoped delivery guarantee sibling isolation between
concurrent executions?** No. This ADR provides a **capability**, not an
automatic guarantee: **execution-scope isolation for executions that
use distinct `EventScope` instances.** Two independent root
`ExecutionContext`s that happen to share the same `EventScope` instance
(e.g. a caller reuses one `EventScope` across unrelated executions)
will see each other's events, by design — isolation is a consequence
of the *caller's choice* to use distinct `EventScope` instances,
exactly as today's global-bus non-isolation is a consequence of there
being exactly one `EventBus` instance. This ADR does not — and cannot
— force distinct scopes onto unrelated executions; it only makes
distinct scopes *possible*, which they are not today. Architecture doc
§5's sibling-isolation requirement is satisfied **when callers use this
capability correctly** (distinct scopes per unrelated root execution),
not automatically for every execution regardless of caller behavior —
this distinction must be preserved everywhere this ADR's outcome is
summarized (requirements matrix, Consequences section below), so that
no future reader concludes "ADR-022 guarantees concurrent sibling
isolation" outright.

**Q9 — Listener-failure isolation?** Not addressed by this ADR —
explicitly deferred, per the project owner's decision during 18C. The
existing, audit-confirmed behavior (a raising listener's exception
propagates out of `publish()`, indistinguishable from a real execution
failure to code further up the stack) is preserved unmodified for both
the global bus and the new `EventScope` type, which has the identical
`publish()` shape. This is named as a real, pre-existing gap in
"Non-goals," not silently inherited without acknowledgment.

**Q10 — Concurrency-safety of listener list mutation?** Not addressed
by this ADR — explicitly deferred, per the project owner's decision
during 18C. `EventScope._listeners` (like `EventBus._listeners`) is an
unsynchronized `list`; concurrent `subscribe`/`unsubscribe`/`publish`
from different threads has the same undefined behavior the existing
`EventBus` already has. Concurrency **tests** for this ADR (see
Testing strategy) verify *isolation between distinct scopes* under
concurrent execution, not thread-safety of a single scope's
subscription list — these are different properties, and only the
former is this ADR's actual requirement (A5/A10 name isolation, not
thread-safe mutation).

**Q11 — Async viability (not implemented, but must not be
foreclosed)?** The `EventScope`/`ExecutionContext.event_scope` design
does not depend on synchronous execution — `EventScope.publish` is a
plain method call, no different in async-compatibility terms than the
existing `EventBus.publish`. A future async execution path would face
the identical async/sync questions this project has already deferred
for `Executor`/`ExecutionEngine` (ADR-018 Q7, ADR-019 Q16) — this ADR
neither solves nor blocks that future work.

**Q12 — Provider independence?** `events.py`'s new `EventScope` class
and `context.py`'s new `event_scope` field import nothing beyond what
`events.py`/`context.py` already import (standard library only,
confirmed by re-reading both files' existing import blocks) — no
provider SDK, matching every prior step's discipline.

## Decision

### Naming and location: `EventScope`, `src/ragtorch/core/events.py`; `ExecutionContext.event_scope`, `src/ragtorch/core/context.py`

`EventScope` added to the existing `events.py` (alongside `EventBus`,
`Event`, `EventType` — the natural home for a delivery-mechanism type).
`ExecutionContext` gains one new, optional, defaulted field in the
existing `context.py`.

### Public contract

`EventScope` and `EventBus` both accept the same `EventListener`
callable — the existing `events.py` type alias (`EventListener =
Callable[[Event], None]`) is reused as-is, not redefined, so the two
delivery primitives share one listener contract and a future
replacement for either can be written against `EventListener` without
knowing which concrete class it is talking to.

`EventScope` has no module-level default instance, no `contextvars`
binding, and no thread-local singleton — ownership is always explicit,
constructed by the caller and threaded through `ExecutionContext`:

```python
scope = EventScope()

context = ExecutionContext(
    event_scope=scope,
)
```

There is no `default_event_scope()` accessor and none is planned —
unlike `event_bus()`, which intentionally exposes the one process-wide
instance, an `EventScope` only exists where a caller explicitly created
one.

```python
# events.py — new addition, alongside the existing EventBus/Event/EventType


class EventScope:
    """Execution-scoped event delivery -- distinct from the global,
    process-wide EventBus (event_bus()). A caller constructs an
    EventScope, subscribes listeners to it, and passes it via
    ExecutionContext(event_scope=...) to observe only that execution's
    (and its nested children's) events, without affecting or being
    affected by the existing global bus.

    Structurally identical to EventBus (subscribe/unsubscribe/publish),
    and accepts the same EventListener callable -- a distinct type, not
    a subclass, so the two are never interchangeable by accident. Not
    thread-safe (see ADR-022 Q10); a raising listener propagates from
    publish() unmodified (see ADR-022 Q9) -- both match EventBus's
    existing, unmodified behavior exactly. There is no module-level
    default instance, no contextvars binding, and no thread-local
    singleton -- an EventScope exists only where a caller explicitly
    constructs one.
    """

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None: ...
    def unsubscribe(self, listener: EventListener) -> None: ...
    def publish(self, event: Event) -> None: ...


# context.py — ExecutionContext gains one new field


@dataclass(frozen=True)
class ExecutionContext:
    run_id: str = field(default_factory=new_run_id)
    parent_run_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_scope: EventScope | None = None  # NEW, additive, default None

    def child(self, **metadata: Any) -> ExecutionContext:
        """Unchanged behavior, plus: event_scope is propagated to the
        child unmodified -- the SAME EventScope object identity
        (child.event_scope is parent.event_scope), not an equal-but-
        distinct instance and not a new one -- so a listener on the
        parent's scope continues to see the whole subtree, exactly as
        the global bus already allows today (see ADR-022 Q4). This is
        an object-identity invariant, not merely an equality one, and
        must be tested with `is` (see Testing strategy, EVT-CHILD)."""
        merged = {**self.metadata, **metadata}
        return ExecutionContext(
            run_id=new_run_id(),
            parent_run_id=self.run_id,
            metadata=merged,
            event_scope=self.event_scope,  # NEW line; everything else unchanged
        )


# module.py — Module.__call__'s existing publish calls, extended additively

# Existing (unchanged): _bus.publish(event) always happens.
# New: if context is not None and context.event_scope is not None,
#      ALSO context.event_scope.publish(event) -- both fire.
```

### Why both the global bus and the scope fire

A caller with a scoped `ExecutionContext` does not lose visibility on
the existing global bus — `event_bus()` subscribers continue to see
every event from every execution, scoped or not, exactly as before.
This is the direct consequence of Q2: nothing about the global bus's
behavior changes. A caller who wants *only* scoped events simply
doesn't subscribe to the global bus.

### Failure semantics and delivery ordering

Both statements below are precise, not aspirational:

> Under normal listener execution, the event is delivered to both
> configured destinations. Existing listener exception propagation is
> preserved and therefore may terminate delivery before a subsequent
> destination is reached.

Concretely: `Module.__call__` calls `_bus.publish(event)` then, if
scoped, `context.event_scope.publish(event)`. If a global-bus listener
raises, `_bus.publish` propagates that exception immediately and
`context.event_scope.publish(event)` is **never reached** — the scope
does not receive that event. Conversely, if global delivery completes
without error and a scope listener then raises, the caller receives
that exception, and the global bus has already received the event.
"Both fire" describes the *intended, normal-path* behavior, not a
transactional or atomic guarantee — this is a direct, unmodified
consequence of Q9's deferred listener-failure isolation, not a new gap
this ADR introduces.

> The relative ordering of delivery between the global `EventBus` and
> an `EventScope` is **not part of the public contract.** A caller
> must not depend on the global bus being notified before, after, or
> atomically with the scope.

This keeps a future implementation (e.g. one that delivers to multiple
scopes, or reorders for performance) free to change without breaking
callers who never observed the ordering as a promise.

### Why `event_scope` defaults to `None`, not to a fresh `EventScope()` per context

A default of `EventScope()` would mean every `ExecutionContext`
constructed anywhere — including every existing test and every
existing caller who never asked for scoping — silently starts paying
the (small, but nonzero) cost of an extra `publish()` call per event,
for a feature they never opted into. `None` makes the additive nature
of this feature explicit and free for existing callers, matching
`StepExecutionContext`/`Block`/`RAGModule`'s consistent precedent of
opt-in additive parameters over defaulted-on infrastructure (e.g.
ADR-018 Q12's rejection of a defaulted-off retry parameter, for the
identical "don't freeze a shape before it's needed" reasoning).

## Non-goals

Explicitly deferred, not part of this decision:

- **Listener-failure isolation.** See Q9. A raising listener's
  exception propagates unmodified, for both `EventBus` and
  `EventScope` — matching today's existing, unaddressed behavior
  exactly.
- **Concurrency-safety of listener-list mutation.** See Q10. Neither
  `EventBus` nor the new `EventScope` synchronizes
  `subscribe`/`unsubscribe`/`publish` — this ADR's concurrency tests
  verify isolation between scopes, not thread-safe mutation of a
  single scope's list.
- **Scoping `Run`, `Trace`, `MetricsCollector`, or `log_event`
  structured logging.** See Q1/Finding 2 — all remain entirely
  unmodified.
- **Changing `event_bus()`'s existing global-delivery semantics.** See
  Q2 — explicitly rejected as an alternative, not merely undone.
- **Async execution support.** See Q11 — not implemented, not
  foreclosed.
- **A serialization format for `EventScope` or scoped events.** Not
  addressed.
- **Automatic per-root-execution `EventScope` creation.** A caller who
  wants isolation must explicitly construct and pass an `EventScope`
  — this ADR does not make `ExecutionEngine.execute`/`execute_plan`
  auto-create one, since no real requirement has yet demonstrated a
  need for automatic (versus explicit, opt-in) scoping.

## Alternatives considered

- **Make `event_bus()` return "the current execution's bus."**
  Rejected — see Q2. Breaks two existing, passing tests and
  reintroduces implicit current-execution state architecture doc §5
  explicitly prohibits.
- **`contextvars`-based implicit ambient scope, set/reset around
  `Module.__call__`.** Rejected — no code in this codebase uses
  `contextvars` or any other implicit/thread-local execution state;
  every existing propagation mechanism (`ExecutionContext` itself,
  `context.child()`, every `context=context` call site) is explicit
  parameter passing. Introducing an ambient mechanism here would be
  the first of its kind in this codebase and would conflict directly
  with architecture doc §5's explicit "no implicit current execution,
  thread-local execution, or context-global execution state is
  introduced" constraint — no evidence from the audit justifies this
  deviation.
- **A second, explicit parameter threaded independently of
  `ExecutionContext`.** Rejected — see Q3. Doubles the propagation
  surface across every existing `context=`-threading call site for no
  benefit `ExecutionContext` doesn't already provide.
- **Give each `.child()` call a fresh `EventScope`.** Rejected — see
  Q4. Would silently break the "listener on parent sees whole subtree"
  property that already exists today via the shared global bus,
  without any test or requirement asking for that regression.
- **Reuse `EventBus` itself as the scope type, with no new class.**
  Rejected — see Q7. Blurs the conceptual distinction between the one
  global compatibility bus and a specific execution's delivery scope.
- **Fix listener-failure isolation and/or concurrency-safety as part
  of this ADR**, since they're closely related and already found by
  the audit. Rejected, per explicit project-owner decision during
  18C — keeps this ADR's scope to exactly what A5/A10 require,
  consistent with every prior step's one-primitive-per-step
  discipline; both remain named, deferred future work.

## Concurrency

Two distinct claims must not be conflated, and this ADR makes both
explicit rather than letting one imply the other:

**Claim A — `EventScope` cross-execution isolation: GUARANTEED,
structurally.** Two distinct `EventScope` instances own two distinct
`_listeners` lists with no reference between them. `scope_a.publish`
iterates only `scope_a._listeners`; there is no code path by which it
can observe or mutate `scope_b._listeners`. This is an ownership/
reference-structure guarantee, proven both by inspection (no shared
state exists to race on) and empirically (18G's
`test_concurrent_executions_do_not_cross_event_scopes`, using
`threading.Barrier` to force genuine overlap, and
`test_concurrent_executions_stay_isolated_across_repeated_runs` over 20
iterations to catch state that a single run might not expose). This
claim holds regardless of thread-safety questions below — it is true
even if the underlying interpreter provided no atomicity guarantees at
all, because the isolation comes from *there being nothing shared*, not
from synchronization.

**Claim B — `EventBus` thread safety: NOT GUARANTEED.** `EventBus` is
shared, mutable, global state (`_bus = EventBus()`,
`src/ragtorch/core/module.py`). `EventBus._listeners` is a plain,
unsynchronized `list`; `subscribe`/`unsubscribe`/`publish` hold no
lock. This ADR does **not** claim `EventBus` is safe under concurrent
subscribe/unsubscribe/publish — individual CPython list operations
being atomic under the GIL does not make the compound
`for listener in self._listeners: listener(event)` loop a specified,
race-free delivery protocol. Concurrent mutation during iteration can,
in principle, skip a listener, observe a listener added mid-iteration,
depend on scheduling for ordering, or behave differently under a future
runtime without CPython's current GIL behavior. 18G's
`test_global_bus_current_concurrent_delivery_behavior_on_cpython`
deliberately does not assert a thread-safety guarantee — it pins one
observed outcome on one interpreter, named accordingly rather than
claiming proof it cannot provide.

Summary table:

| Property | Guarantee |
| --- | --- |
| `EventScope` cross-execution isolation | **GUARANTEED** (structural — no shared state) |
| `EventBus` thread safety | **NOT GUARANTEED** |
| `EventBus` concurrent ordering | **NOT GUARANTEED** |
| `EventBus` concurrent subscribe/unsubscribe semantics | **NOT GUARANTEED** |
| `EventBus` exception isolation (any concurrency) | **NOT GUARANTEED** (pre-existing, unrelated to concurrency — see Q9) |

Adding synchronization to `EventBus` is explicitly **not** part of this
ADR (see Non-goals) and must be treated as a future architectural
change, not a bug fix — synchronization can alter ordering, reentrancy,
latency, and exception-propagation behavior, all of which are currently
unspecified and therefore free to change without breaking a documented
contract. Making that change without an ADR would silently convert an
undocumented absence of a guarantee into an implicit one. See Deferred
Risks (EVT-RACE-001) below.

## Security

### Preliminary (18C, design-time)

`EventScope.publish` performs exactly the operation `EventBus.publish`
already establishes as trusted: calling caller-subscribed listener
functions with an `Event`. No new data is added to `Event`'s existing
fields; scoping changes *who receives* an event, not *what an event
contains*. No automatic cross-execution data exposure is introduced —
if anything, the opposite: a caller using `EventScope` gains a way to
*avoid* incidentally observing unrelated executions' events, which the
global-bus-only design forces on every subscriber today.

### Expanded (18K, implementation-verified)

Re-verified against the actual merged implementation, not re-asserted
from design intent:

- **`Event.payload` content is unchanged by this ADR.** Grepped every
  `payload=` construction site in `module.py`: both remain
  `payload={"error": str(exc)}` on the `MODULE_FAILED` path, in both
  the `context is None` and `context is not None` branches —
  byte-identical to pre-ADR-022 `main`. `EventScope` never constructs,
  reads, or transforms a payload; it only routes an already-constructed
  `Event` object to an additional destination (Decision section). No
  new data-exposure surface exists because no new data exists.
- **Cross-execution observability is opt-in, not automatic.** A
  listener only receives events for executions whose caller explicitly
  passed it the same `EventScope` instance (Q8). This is a *narrowing*
  of the pre-existing default (the global bus already exposes every
  execution's events to every global subscriber) — `EventScope`
  strictly reduces, never increases, what an arbitrary listener can
  observe by default.
- **Listener retention of sensitive event objects**: unchanged from
  `EventBus`'s pre-existing behavior — a listener can retain a
  reference to any `Event` it receives (Python has no mechanism to
  prevent this for either bus type), a pre-existing property of the
  publish/subscribe pattern itself, not introduced or worsened by this
  ADR.
- **Trust boundary**: `EventScope`, like `EventBus`, executes
  caller-subscribed callables synchronously and in-process — the trust
  boundary is "code that can call `.subscribe()`," identical to today.
  No new caller-untrusted input crosses into `EventScope`/`Event`
  construction; `run_id`/`parent_run_id` are UUIDs generated internally
  (`new_run_id()`), never user-supplied strings reflected back.
- **No new secret-leakage path**: confirmed no `vars()`/`__dict__`
  introspection was added anywhere in the diff (`git diff main...HEAD
  -- src/` re-read in full for this review) — the only new code is
  `EventScope`'s four methods (`__init__`/`subscribe`/`unsubscribe`/
  `publish`) and the additive dual-publish calls in `Module.__call__`,
  none of which read component internal state.

## Dependency review

### Preliminary (18C, design-time)

Zero new runtime dependencies. `events.py`'s new `EventScope` class
and `context.py`'s new `event_scope` field use only what those two
files already import (standard library `dataclasses`, `typing`,
`collections.abc`) — no provider SDK, no `threading`/`contextvars`
(neither is used, per Q10/the rejected `contextvars` alternative).

### Expanded (18K, implementation-verified)

Re-confirmed against the actual merged diff, not re-asserted:
`git diff main...feat/step18-event-scoped-delivery-audit -- pyproject.toml
requirements.txt setup.py setup.cfg` returns **zero changes** — no
dependency manifest was touched anywhere in this branch. Direct read of
`events.py`'s import block confirms only `logging`, `time`,
`collections.abc.Callable`, `dataclasses`, `enum.Enum`, `typing.Any` —
all standard library, unchanged from before this ADR plus zero
additions beyond what `EventScope` itself needs (which turned out to be
nothing beyond what `EventBus` already imports). No dependency
necessity/license/maintenance-status review is required because no
dependency was added.

## Compatibility

### Preliminary (18C, design-time)

`EventBus`, `Event`, `EventType`, `event_bus()` — all unchanged in
behavior; `EventScope` is a pure addition to `events.py`.
`ExecutionContext`'s existing three fields (`run_id`, `parent_run_id`,
`metadata`) and its existing `child()` behavior for those three fields
are unchanged; `event_scope` is a new, defaulted (`None`) field —
every existing `ExecutionContext(...)` call site, with zero code
changes, continues to behave identically, since `event_scope` defaults
to `None` and `Module.__call__`'s new scoped-publish branch is a
no-op whenever it is `None` (Q6). `Module.__call__`'s existing publish
call sites, `Run`, `Trace`, `MetricsCollector`, `ExecutionEngine`,
`Sequential`, `Block`, `RAGModule` — all unchanged.

### Expanded (18K, implementation-verified)

- **API**: existing imports unchanged (`EventScope` is a pure addition
  to both `ragtorch.core.__all__` and `ragtorch.__all__`, verified by
  API-01); existing signatures unchanged (`ExecutionContext.__init__`,
  `Module.__call__`, `event_bus()` all keep their exact prior
  parameter lists — `event_scope` is appended as a new, defaulted
  dataclass field, which does not change any positional-argument
  contract); existing defaults unchanged (every default value on every
  pre-existing parameter is untouched); existing exceptions unchanged
  (`ExecutionError`/`RegistryError` propagation paths in
  `Module.__call__` are structurally identical to pre-ADR-022 `main`,
  confirmed by the diff showing only additive lines around the
  existing `try`/`except` blocks, no restructuring).
- **Behavioral**: existing ordering preserved (global-bus publish
  still happens first, unconditionally, exactly as before — the scoped
  publish is a new line appended after it, never reordered ahead of
  it); existing failure propagation preserved (COMPAT-01/COMPAT-02
  regression tests, CI-proven, assert the pre-existing
  `test_events.py` suite passes unmodified); existing observability
  preserved (`log_event`/`Run`/`Trace`/`MetricsCollector` are untouched
  by this diff — confirmed zero references to any of those names in
  the changed lines of `events.py`/`context.py`/`module.py`).
- **Serialization**: not applicable — neither `EventBus` nor the new
  `EventScope` was, is, or is claimed to be serializable; `Event`
  itself (a frozen dataclass) was already not addressed by any
  pickle/JSON contract before this ADR, and remains unchanged.
- **Runtime**: supported Python versions unaffected — CI-proven green
  on 3.10/3.11/3.12 (PR #25, run `32037264224`); no new sync/async
  distinction introduced (`EventScope.publish` is a plain synchronous
  method, matching `EventBus.publish` exactly); no new thread/process
  behavior claimed (see Concurrency section above — Claim B explicitly
  states no new guarantee, not even an implicit one, is introduced).

## Testing strategy

- **EVT-01** `EventScope.subscribe`/`publish`/`unsubscribe` behave
  identically to `EventBus`'s existing, already-tested shape (mirrors
  `test_event_bus_publishes_to_subscribers`/
  `test_unsubscribe_stops_delivery` for the new type). Assertions are
  behavioral (`assert received == [event]`), never on internal
  representation (never `len(scope._listeners)`).
- **EVT-NOCTX-01** `context=None`: publishes to the global bus only;
  `run_id=None`; no `EventScope` is touched or required to exist —
  the exact contract-diagram case at the top of this ADR.
- **EVT-NOCTX-02** `context=ExecutionContext(event_scope=None)`
  (the default): publishes to the global bus only — identical
  observable behavior to EVT-NOCTX-01's global-bus delivery, proving
  the default is truly inert.
- **EVT-03** `context=ExecutionContext(event_scope=scope)`: publishes
  to **both** the global bus and `scope` — both receive the same
  lifecycle events (`MODULE_STARTED`/`MODULE_FINISHED`), under normal
  (non-raising) listener execution.
- **EVT-CHILD** `parent = ExecutionContext(event_scope=scope);
  child = parent.child()` — asserts `child.event_scope is
  parent.event_scope` (object identity via `is`, not `==`), pinning
  Q4's decision precisely enough that a future implementation cannot
  satisfy the test by passing an equal-but-distinct `EventScope`.
- **EVT-ORDER** A listener that mutates shared state on both the
  global bus and the scope for the same event confirms only that both
  destinations *eventually* observe it under normal execution — the
  test must not assert *which* destination is notified first, per the
  ordering non-contract above.
- **EVT-FAILSTOP** A raising global-bus listener causes
  `context.event_scope.publish` to never be invoked for that event
  (verified via a scope listener that must NOT have been called) —
  the direct regression test for the "failure may terminate delivery
  before a subsequent destination is reached" contract.
- **EVT-04** Two independent root `ExecutionContext`s, each with its
  own distinct `EventScope`, run sequentially: scope A's listener
  receives only A's events; scope B's listener receives only B's
  events; neither receives the other's — proving isolation between
  unrelated executions.
- **EVT-05 (nested)** A `Sequential(A(), B())` called with a scoped
  root `ExecutionContext`: the scope's listener receives events from
  `Sequential`, `A`, and `B` — proving `.child()` propagates the same
  scope, matching Q4's decision and the audit's own empirical
  `Sequential` construction.
- **EVT-06 (sibling delivery, the actual A5/A10 requirement)** Two
  `Sequential`s, each with its own root `ExecutionContext`/`EventScope`,
  each containing two `Module` children: scope A's listener never
  receives any event whose `run_id`/`parent_run_id` traces to scope
  B's tree, and vice versa — the direct regression test for the gap
  this ADR exists to close.
- **EVT-07 (concurrent isolation)** Two executions, each with its own
  `EventScope`, run on separate threads with deterministic
  synchronization (`threading.Barrier`/`threading.Event`, never
  `time.sleep`) so both executions genuinely overlap in wall-clock
  time: each scope's listener receives only its own execution's
  events — proving isolation holds under real concurrency, not merely
  sequential calls. Explicit thread cleanup (`thread.join(timeout=...)`,
  asserting no leaked thread) to keep CI from hanging on a bug.
- **EVT-08 (failure)** A component failure inside a scoped execution:
  `MODULE_FAILED` is published to both the global bus and the scope,
  exactly as `MODULE_STARTED`/`MODULE_FINISHED` already are —
  consistent handling across all three lifecycle event types.
- **EVT-09 (listener-failure behavior, documented not fixed)** A
  raising listener on an `EventScope` causes `publish()` to raise,
  exactly as it already does for `EventBus` — an explicit test pinning
  the current, deferred (Q9) behavior, not an aspirational one.
- **COMPAT-01** `tests/unit/core/test_events.py`'s full existing suite
  passes unmodified.
- **COMPAT-02** `Module`/`Sequential`/`Block`/`RAGModule`'s full
  existing test suites pass unmodified.
- **API-01** `EventScope` appears in both `ragtorch.core.__all__` and
  `ragtorch.__all__`, verified by the existing public API parity test,
  and is importable both ways:
  `from ragtorch.core import EventScope` and
  `from ragtorch import EventScope`.

## Benchmark strategy

Per ADR-009, `benchmarks/step18_event_scoped_delivery.py`. Three
tiers, not two, to separate "checking whether a scope is configured"
overhead from "actually delivering to a subscribed listener" overhead:

```text
1. no scope        -- context.event_scope is None (today's exact path)
2. empty scope      -- event_scope=EventScope() with zero subscribers
3. active scope      -- event_scope=EventScope() with one subscriber
```

Reported as median/distribution over repeated runs at a fixed, small
`Sequential` chain length. Tier 2 vs. tier 1 isolates the cost of the
`context.event_scope is not None` check and the extra `publish()` call
with no listeners; tier 3 vs. tier 2 isolates the cost of actual
listener invocation. As with every prior benchmark in this project:
measures, does not prove, an overhead claim; no threshold assertion;
not wired into CI as a blocking gate.

## CI strategy

A green existing suite (431/431) proves the repository remains stable;
it does not by itself prove ADR-022's contract is implemented
correctly. CI for Step 18's implementation phase must run, at minimum:

```text
formatting        (ruff format --check)
lint              (ruff check .)
type checking     (mypy)
unit suite        (including EVT-* tests above)
integration suite (Sequential/Block/RAGModule/ExecutionEngine, COMPAT-01/02)
public API parity (API-01, both import paths)
ADR-022-specific tests explicitly enumerated, not merely swept in by
                  the full-suite run
benchmark smoke   (the three-tier benchmark executes without error;
                  not a blocking performance gate)
documentation/architecture checks (requirements matrix updated,
                  ADR status references correct)
```

## Consequences

- A caller can observe only their own execution's (and its nested
  children's) lifecycle events, closing the gap A5/A10 have named
  since Step 4, by **providing the execution-scoped delivery mechanism
  required to satisfy §5's sibling-isolation requirement when unrelated
  root executions use distinct `EventScope` instances** (see Q8) — the
  one part of that invariant not already satisfied at the identity
  layer. This is a capability, not an automatic guarantee: callers who
  share one `EventScope` across unrelated executions do not get
  isolation, by design (see Q8).
- `event_bus()`'s existing, tested global semantics are completely
  unchanged — zero risk to any existing caller, verified by explicit
  regression tests (COMPAT-01/02), not merely assumed from "we didn't
  edit that function."
- The audit-confirmed listener-failure and concurrency-safety gaps are
  named, tested as their current (unfixed) behavior, and explicitly
  deferred — not silently inherited, not opportunistically fixed
  outside this ADR's actual scope.
- `Run`/`Trace`/`MetricsCollector`/structured logging remain entirely
  separate from event delivery, exactly as they are today — this ADR
  does not begin unifying RAG-MODULE's three disjoint observability
  channels, a larger question explicitly out of scope here.
- Scope stays deliberately narrow: no listener-failure fix, no
  concurrency-safety fix, no `Run`/logging scoping, no async, no
  serialization, no automatic scope creation — consistent with every
  prior step's discipline.

## Deferred Risks

Formal record of known, intentionally-unfixed gaps carried forward by
this ADR — recorded so "deferred" does not silently become "forgotten."

### EVT-RACE-001 — Global `EventBus` synchronization

**Status:** Deferred — re-audited in Step 21 (21A-21C), decision
unchanged: no synchronization added.

**Current behavior:** `EventBus` (the global, process-wide instance
returned by `event_bus()`) uses a shared, mutable, unsynchronized
`list` for its listener registry. No lock or other synchronization
primitive guards `subscribe`/`unsubscribe`/`publish`.

**Why deferred:** Adding synchronization is an architectural change,
not a bug fix — it can alter ordering, reentrancy, latency, and
exception-propagation behavior that are all currently unspecified. It
is unrelated to ADR-022's actual scope (execution-scoped *delivery*,
not global-bus *safety* — see Problem/Q1), and fixing it here would
violate this project's one-primitive-per-step discipline.

**Step 21 audit findings (deterministic, `threading.Barrier`-synchronized
reproductions, not `time.sleep`-based, not theoretical):** aggressive
concurrent subscribe/unsubscribe/publish churn (up to 20,000
iterations, up to 4-way concurrent publish) produced **zero
memory-corruption or crash hazards** — CPython's GIL protects every
individual `list` operation, and Step 20's `publish()`-time snapshot
already isolates each call from concurrent mutation cleanly. The one
real, deterministically-reproducible finding: **two threads
concurrently calling `unsubscribe()` on the *same* listener can race,
with the losing thread raising `ValueError`.** This is **not a new
concurrency-specific defect** — confirmed empirically that
`unsubscribe()` on an already-removed listener already raises
`ValueError` with zero threads involved (i.e., `unsubscribe()` was
never idempotent, single- or multi-threaded); concurrency only makes
this pre-existing, already-true contract question reachable
non-deterministically rather than introducing a new failure mode.
Making `unsubscribe()` idempotent would be an unrelated API-contract
decision this audit found no evidence to justify (no caller has ever
needed it).

**Current guarantee:** None. See the Concurrency section above for the
full table. `EventScope` isolation is unaffected by this risk (Claim A
holds independently of Claim B).

**Evidence:** `test_global_bus_current_concurrent_delivery_behavior_on_cpython`
(18G) pins one observed outcome on CPython. Step 21 adds five
parametrized characterization tests (`EventBus`/`EventScope` both) in
`tests/unit/core/test_events.py`:
`test_concurrent_subscribe_does_not_corrupt_or_lose_registrations`,
`test_concurrent_publish_delivers_every_event_no_loss_no_duplication`,
`test_concurrent_subscribe_and_publish_does_not_crash`,
`test_concurrent_unsubscribe_of_the_same_listener_can_race_to_valueerror`,
`test_double_unsubscribe_already_raises_single_threaded`. None of
these establish a thread-safety *guarantee* — they pin observed
behavior on CPython, exactly like the 18G test before them.

**Required before changing:** a concurrency ADR amendment (or new ADR)
addressing ordering, reentrancy, exception isolation, and listener
lifecycle under synchronization; a benchmark showing the latency/
contention cost of the chosen synchronization primitive; deterministic
race tests (not schedule-dependent stress tests); a compatibility
analysis against every existing `event_bus()` caller; CI evidence.
Step 21's audit did not find evidence meeting this bar — see
`evaluation/step21-evaluation.md`.

**Owner:** Unassigned — revisit when a real requirement (not merely
audit-discovered risk) demands `EventBus` concurrency guarantees. Two
audits now (Step 18's original recording, Step 21's re-audit) have
found no such requirement.

**Revisit:** No committed milestone. Tracked here so it surfaces on the
next audit that touches `events.py`.

### EVT-FAIL-001 — Listener-failure isolation (both `EventBus` and `EventScope`)

**Status:** Deferred (originated in 18B/18C, Q9; unchanged by 18G).

**Current behavior:** A raising listener's exception propagates out of
`publish()` unmodified, indistinguishable from a real execution
failure to code further up the stack, for both `EventBus` and
`EventScope`.

**Why deferred:** Unrelated to this ADR's scoping requirement (A5/A10);
fixing it would be an opportunistic change outside the frozen contract
— explicitly forbidden per the project's 18C guidance ("do not
opportunistically fix").

**Current guarantee:** None. Pinned by `test_event_scope_preserves_listener_exception_behavior`,
`test_global_listener_failure_prevents_scope_delivery`, and
`test_scope_listener_failure_propagates` (18D/18E).

**Required before changing:** a dedicated ADR addressing whether/how
listener isolation should work (try/except per listener? first-failure-
wins? aggregate exceptions?), since any choice changes existing,
depended-upon behavior for `EventBus` callers.

**Owner:** Unassigned.

**Revisit:** No committed milestone.
