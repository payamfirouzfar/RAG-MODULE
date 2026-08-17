# Step 18B — Source/Design Audit: Execution-Scoped Event Delivery

Date: 2026-08-17

Branch: `feat/step18-event-scoped-delivery-audit`, based on `main` at
`160cc7a` (confirmed clean, 431/431, before any file in this audit was
created).

## Purpose

Answer the 12 decision-gate questions from source, not assumption,
before ADR-022 is drafted. **No implementation mechanism is chosen in
this document.** `contextvars`, a scoped `EventBus`, and a modified
`Module.__call__` are all still open candidates.

## Files read in full

`context.py`, `run.py`, `events.py`, `module.py`, `engine.py` — all
five, complete, not excerpted. `execution.py` (the ADR-018
Executor/`StepHandler` module — a different "execution" than this
audit's subject) was grepped, not re-read in full, since 18A already
established it and `execution_plan.py` never touch events (confirmed
by grep: zero matches for `event`/`_bus`/`publish` in either).
`sequential.py`/`block.py` grepped and confirmed to contain zero event
references.

## Execution lifecycle map (built from source, not assumed)

```text
caller
  |
  v
Module.__call__(input, *, context=None)
  |
  +-- context is None branch:
  |     _bus.publish(MODULE_STARTED, name)      <- run_id=None always
  |     forward(input)  [no context passed]
  |     _bus.publish(MODULE_FINISHED, name)      <- run_id=None always
  |     (on exception: _bus.publish(MODULE_FAILED, ...), then
  |      wrap as ExecutionError unless RegistryError)
  |
  +-- context is not None branch:
        _bus.publish(MODULE_STARTED, name, run_id=context.run_id,
                      parent_run_id=context.parent_run_id)
        forward(input, context=context) if forward accepts context,
              else forward(input)  [context silently dropped from the
              child call -- see Finding 3]
        _bus.publish(MODULE_FINISHED, name, run_id=..., parent_run_id=...)
        (on exception: _bus.publish(MODULE_FAILED, ...), same wrap rule)
```

`_bus` is `src/ragtorch/core/module.py:25`'s single module-level
global `EventBus()` instance. **Every** `Module.__call__` on **every**
`Module` subclass in the process — `Sequential`, `Block`,
`_GraphBackedRAGModule`, any user subclass — publishes to this exact
same instance. There is no other event-publishing code path anywhere
in `src/ragtorch/core` (confirmed by grep: `publish(` appears only in
`module.py`).

```text
ExecutionEngine.execute(module, input, context=None)
  |
  +-- context = context or ExecutionContext()
  +-- run = Run.start(context)          <- Run is engine-local, not published
  +-- trace = Trace(); metrics = MetricsCollector()
  +-- module(input, context=context)    <- delegates to Module.__call__ above,
  |                                         which does its own, entirely
  |                                         separate _bus.publish(...) calls
  +-- run.succeed(output) / run.fail(exc)
  +-- returns ExecutionResult(run, trace, metrics)

ExecutionEngine.execute_plan(plan, handler, *, context=None, executor=None)
  |
  +-- same Run/Trace/Metrics shape as execute()
  +-- plan_executor.execute(plan, handler)   <- calls handler(step, step_context)
  |                                              per ADR-018/019; handler is
  |                                              caller-supplied and opaque --
  |                                              the engine never touches
  |                                              _bus here, and neither does
  |                                              Executor/SequentialExecutor
  |                                              (confirmed: execution.py has
  |                                              zero event references)
  +-- run.succeed(output) / run.fail(exc)
```

**Finding 1 (load-bearing)**: `ExecutionEngine` and `Run` are **entirely
disjoint** from the event system. `Run`'s lifecycle (`PENDING → RUNNING
→ {SUCCEEDED, FAILED, CANCELLED}`) is never published as an `Event`.
`ExecutionEngine.execute`'s own `log_event(...)` calls (DEBUG-level
structured logging, `logging.py`) are also a **third**, separate
mechanism, unrelated to `EventBus`/`Event`. There are, today, three
independent, non-integrated signal channels: (a) `Module.__call__`'s
`EventBus`/`Event`, (b) `ExecutionEngine`'s `Run`/`Trace`/`MetricsCollector`,
(c) `ExecutionEngine`'s `log_event` structured logging. Any ADR-022
design must state explicitly which of these it scopes — the audit
finds no basis for assuming "scope events" implicitly also means
"scope Run" or "scope logging."

```text
Block.forward(input, *, context=None)
  |
  +-- builds a StepHandler closure over components + context
  +-- ExecutionEngine().execute_plan(plan(self._graph), handler, context=context)
  |     (fresh, unscoped ExecutionEngine instance every call --
  |      confirmed: no engine=/executor= parameter exists on Block)
  +-- returns result.output.values[self._output_node]

  Block itself is a Module (inherits Module.__call__), so calling a
  Block ALSO triggers Module.__call__'s own _bus.publish(...) for the
  Block's own MODULE_STARTED/FINISHED/FAILED -- entirely independent
  of whatever happens inside its own execute_plan() call, which
  publishes nothing to _bus at all (Executor/StepHandler layer has no
  event awareness, confirmed above).

_GraphBackedRAGModule.forward(input, *, context=None)
  |
  +-- self._block(input, context=context)   <- through Module.__call__,
        exactly as Sequential invokes children (confirmed in ADR-021's
        own audit) -- so _GraphBackedRAGModule ALSO independently
        publishes its own MODULE_STARTED/FINISHED/FAILED via _bus,
        nested one layer above Block's own publish calls.
```

**Finding 2**: `RAGModule.from_graph(...)` results and `Block`
instances both publish events for themselves via `Module.__call__` —
but nothing published from *inside* their own `execute_plan()` call
(no per-step events; confirmed above). So today, calling a `Block`
produces exactly 2 events (`MODULE_STARTED`/`MODULE_FINISHED` for the
`Block` itself) regardless of how many nodes its graph contains — the
graph's internal component calls are invisible to the event system
entirely, unless those components are themselves `Module` subclasses
(in which case each one independently publishes via its own
`Module.__call__`, since `Block`'s handler calls
`components[step.node_id](upstream, context=context)` — a bare
`Component.__call__`, and if that `Component` happens to be a
`Module`, it goes through `Module.__call__`'s publish path too).

**Finding 3 (real, unrelated bug candidate, noted not fixed)**: line
150-153 of `module.py` — if `context is not None` but
`_forward_accepts_context(type(self))` is `False`, the child call is
`self.forward(input)` with **no context argument at all** — the
context is silently dropped from `forward`, even though the *events*
(`MODULE_STARTED`/`FINISHED`) for that same call still carry
`run_id`/`parent_run_id`. This is a pre-existing (Step 4) behavior,
not something Step 18 introduces, and out of this audit's scope to
fix — noted because a badly-scoped event-delivery design could make
this inconsistency more visible, not because it needs to be fixed now.

## Empirical verification: nested `Sequential` identity (not assumed)

Constructed directly (`Sequential(A(), B())`, `A`/`B` bare `Module`s,
root `ExecutionContext`, one subscribed listener recording every
event):

```text
MODULE_STARTED  Sequential  run_id=R0                parent=None
MODULE_STARTED  A           run_id=R1                parent=R0
MODULE_FINISHED A           run_id=R1                parent=R0
MODULE_STARTED  B           run_id=R2                parent=R0
MODULE_FINISHED B           run_id=R2                parent=R0
MODULE_FINISHED Sequential  run_id=R0                parent=None
```

**Root run identity**: holds (`Sequential`'s `run_id` is the caller-
supplied context's `run_id`). **Parent-child relationship**: holds
(`A`/`B`'s `parent_run_id` both equal `Sequential`'s `run_id`).
**Sibling distinguishability**: holds at the *identity* level (`A`
and `B` get distinct `run_id`s, both correctly parented) — matching
`test_nested_context_events_remain_distinguishable`'s existing,
passing assertion pattern (`if e.run_id == child.run_id`).
**Sibling isolation at *delivery*: does not hold** — the one
subscribed listener received all six events, interleaved, with no
mechanism to receive only `A`'s or only `B`'s. This is the exact,
now-empirically-confirmed gap Step 18A named from the architecture
doc's §5 requirement, not merely inferred from stale prose.

## Lifecycle/ownership table

| Concept | Created where? | Immutable? | Lifetime | Nested? | Public? |
| --- | --- | --- | --- | --- | --- |
| `ExecutionContext` | Caller, or `Module.__call__`/`ExecutionEngine.execute`/`execute_plan` default to `ExecutionContext()` if none supplied | Yes (`frozen=True`, `metadata` copied into `MappingProxyType`) | One execution's identity; `child()` produces a new, independent instance — no shared mutable state between parent/child | Yes, via `.child()` — `run_id`/`parent_run_id` chain | Yes (`ragtorch.core.context.ExecutionContext`, exported) |
| `Run` | `ExecutionEngine.execute`/`execute_plan` only, via `Run.start(context)` — **never created by bare `Module.__call__`** | No — mutable dataclass, one-shot terminal transition enforced by `_finish` | One `ExecutionEngine` call; discarded after `ExecutionResult` is returned (no retention) | No inherent nesting concept of its own — nesting comes entirely from the `ExecutionContext` it wraps | Yes (`ragtorch.core.run.Run`, exported), but only reachable via `ExecutionEngine`'s return value — `Module.__call__` alone never produces one |
| `EventBus` (`_bus`) | Once, at `module.py` import time, module-level global | No — `_listeners: list` is mutable, grows/shrinks via `subscribe`/`unsubscribe` | Process lifetime — never recreated, never scoped | No — flat list, no concept of nesting or scope at all | Yes, via `event_bus()` (exported) — the *instance* is singular; a caller can construct their own `EventBus()` too (confirmed: `test_event_bus_publishes_to_subscribers` does exactly this), but `Module.__call__` only ever publishes to the one global `_bus`, never a caller-supplied one |
| `Event` | `Module.__call__`, inline, once per lifecycle transition (STARTED/FINISHED/FAILED) | Yes (`frozen=True`) | One event; not retained anywhere after `publish()` returns (no history) | N/A — carries `run_id`/`parent_run_id` as plain optional string fields, not a nested structure | Yes (`ragtorch.core.events.Event`, exported) |

## Answers to the 12 decision-gate questions (evidence-backed)

**1. What is the execution boundary?** Two candidate boundaries exist
in the source today, and they are **not the same thing**: (a) one
`Module.__call__` invocation (the boundary that actually publishes
events), and (b) one `ExecutionEngine.execute`/`execute_plan` call
(the boundary that owns `Run`). A bare `module(input, context=ctx)`
call with no `ExecutionEngine` involved still publishes events but
never creates a `Run`. This distinction must be preserved, not
collapsed, in ADR-022 — scoping "by `Run`" and scoping "by `Module.__call__`"
are different designs with different consequences for the (very
common, already-tested) no-engine call path.

**2. Who creates `ExecutionContext`?** The caller, or
`ExecutionEngine.execute`/`execute_plan` via `context = context or
ExecutionContext()` when none is supplied. **`Module.__call__` never
creates one.** Its two branches are a real fork, not a default-filling
pattern: `context is None` takes an entirely separate, context-free
code path (publishing events with `run_id=None`, never touching
`ExecutionContext` at all), while `context is not None` takes the
context-aware path and threads the caller-supplied object through.
So there is no single creation point — but more precisely, only two
of the three relevant call sites (`ExecutionEngine.execute`,
`execute_plan`) ever construct a default `ExecutionContext`;
`Module.__call__` either receives one or runs the context-free branch,
never manufacturing one itself.

**3. Who creates `Run`?** Exclusively `ExecutionEngine.execute`/
`execute_plan`, via `Run.start(context)`. A bare `Module.__call__`
never creates one. This confirms Q1's finding: `Run` is not a
universal execution-boundary marker, only an `ExecutionEngine`-scoped
one.

**4. Who owns `EventScope`?** No such concept exists in the source
today — this is a design question ADR-022 must answer, not something
this audit can report from existing code. What *does* exist: nothing
currently reads or writes anything on `ExecutionContext` related to
events at all — `ExecutionContext` and `EventBus` are, today,
completely uncoupled types that happen to both get passed information
into the same `Module.__call__` call.

**5. How does scope propagate?** N/A today — no scope exists. What
*does* propagate correctly today is `ExecutionContext` itself, via
explicit parameter passing (`context=context`) at every call site
that supports it (`Module.__call__` → `forward`, `Sequential.forward`
→ children via `context.child(...)`, `Block.forward` → its handler
closure, `_GraphBackedRAGModule.forward` → `self._block`). Any future
scope-propagation mechanism has this same explicit-parameter-passing
precedent to match, per architecture doc §5's "no implicit current
execution... is introduced" constraint — **not** a `contextvars`-style
implicit ambient mechanism, unless ADR-022 explicitly justifies
diverging from every other propagation mechanism in this codebase.

**6. How does nested execution behave (identity)?** Confirmed
empirically above: correct root/parent/child `run_id` chaining,
verified by direct construction, not merely by re-reading
`ExecutionContext.child()`'s docstring.

**7. How do siblings behave (identity vs. delivery)?** Identity:
correct (distinct `run_id`s, correctly parented — confirmed
empirically). Delivery: **not isolated** — confirmed empirically, the
actual gap.

**8. What does `event_bus()` mean after Step 18?** Not decided by this
audit — but the existing test suite (`test_events.py`) is direct
evidence for what it means *today*: a single, shared, global,
un-scoped bus that every `Module.__call__` publishes to, and that
tests already filter manually (`if e.module_name == "..."`,
`if e.run_id == ...`). Any ADR-022 design that silently redefines this
function's return value's *scope* (e.g. making it return "the current
execution's bus" instead of "the global bus") breaks
`test_module_call_emits_started_and_finished_events` and
`test_nested_context_events_remain_distinguishable`'s existing,
passing assertions, which rely on `event_bus()` returning one bus that
sees everything.

**9. What happens without `ExecutionContext`?** Confirmed by source:
`Module.__call__`'s `context is None` branch publishes events with
`run_id=None`/`parent_run_id` field omitted (defaults to `None`) —
this is existing, tested behavior
(`test_module_call_emits_started_and_finished_events` asserts
`all(e.run_id is None for e in received if e.module_name == "Echo")`).
Any scoping mechanism must define what "no context" means for scope
too — likely "falls back to the existing global-bus behavior,"
matching every other additive-not-breaking precedent in this project,
but this is a decision for ADR-022, not concluded here.

**10. What happens if an event listener fails?** Confirmed by source:
**undefined and unguarded**. `EventBus.publish`'s loop
(`for listener in self._listeners: listener(event)`) has no
`try`/`except` — a raising listener's exception propagates straight
out of `publish()`, straight out of `Module.__call__`, indistinguishable
from a real component failure to any code further up the call stack.
This is a **pre-existing gap**, not something Step 18 introduces —
noted here because ADR-022 must decide whether execution-scoped
delivery changes this (e.g. isolating listener failures per scope) or
explicitly preserves the current, unguarded behavior and states so.

**11. What happens during concurrent execution?** Not tested anywhere
in the existing suite (confirmed: no `threading`/`concurrent.futures`
import anywhere in `tests/`). `EventBus._listeners` is a plain
`list`, mutated by `subscribe`/`unsubscribe` with no lock — concurrent
`subscribe`/`unsubscribe`/`publish` calls from different threads today
have undefined behavior (ordinary Python list mutation races). This is
the concrete gap the matrix's own stale "concurrency tests" item names
— confirmed real, not hypothetical.

**12. What is the smallest additive public API?** Not decided by this
audit. The audit's contribution is narrowing the design space: any
proposal must (a) preserve `event_bus()`'s current global,
un-scoped, `run_id`-filterable behavior exactly (Q8), (b) not
introduce implicit ambient/thread-local execution state unless
explicitly justified against architecture doc §5's stated constraint
(Q5), (c) explicitly state whether it scopes `Run`, `Event`, or both,
given they are today entirely disjoint systems (Finding 1), and (d)
explicitly state its listener-failure and no-context behavior (Q9/Q10)
rather than leaving them to be discovered.

## What this audit deliberately does not decide

Per the explicit instruction governing this phase: **no implementation
mechanism is chosen here.** `contextvars`, a scoped `EventBus`
subclass, `ExecutionContext` gaining an `event_scope` field, or
`ExecutionEngine`-owned delivery are all still open. This document's
job was to make the actual, current behavior undeniable so ADR-022
can be written against facts, not inference — matching the discipline
already used for 16B/17B before ADR-020/021.

## Next step

ADR-022, addressing all 12 questions explicitly, per the same
structure ADR-018 through ADR-021 used (Context/Problem/Open
Questions/Decision/Non-goals/Alternatives/Security/Dependency/
Compatibility/Testing/Benchmark/Consequences). Not drafted in this
document.
