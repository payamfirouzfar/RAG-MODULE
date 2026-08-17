# ADR-023: Event Listener Failure Isolation

## Status

Proposed

## Context

`EventBus` and `EventScope` (`ragtorch.core.events`, ADR-003/ADR-022)
both publish events via the identical compound loop:

```python
def publish(self, event: Event) -> None:
    for listener in self._listeners:
        listener(event)
```

ADR-022 recorded this as a formal deferred risk, **EVT-FAIL-001**,
at the time explicitly out of scope for that ADR's own contract
("do not opportunistically fix"). This ADR is the dedicated follow-up
EVT-FAIL-001's own record calls for.

**Empirically confirmed (20A audit, not assumed from EVT-FAIL-001's
prose) on current `main` (`dd019c6`):**

```python
bus = EventBus()
bus.subscribe(listener_a)  # raises RuntimeError("boom")
bus.subscribe(listener_b)  # never called
bus.publish(event)  # raises RuntimeError; listener_b is silently skipped
```

A raising listener does not merely fail loudly — it silently prevents
delivery to every listener subscribed after it, with no way for the
caller to know `listener_b` never ran. This is a real defect class
(silent partial delivery), not a speculative concern.

## Problem

Choose and implement an explicit listener-failure policy for both
`EventBus` and `EventScope`, replacing the current unspecified,
accidental "first exception wins, everything after is silently
skipped" behavior, without introducing a new architectural decision
beyond this narrow scope (concurrency/synchronization — EVT-RACE-001 —
remains explicitly excluded; see Non-goals).

## Decision

**Isolate-and-continue, aggregate exceptions.** `publish()` invokes
every subscribed listener even if an earlier listener raised. Every
listener's exception is caught individually; if one or more listeners
raised, `publish()` raises a single new exception,
`ListenerDeliveryError`, after every listener has been given the
chance to run — carrying the original event and every
`(listener, exception)` pair that failed, in delivery order.

### Why not `ExceptionGroup`?

Python's native `ExceptionGroup` (PEP 654) requires Python 3.11+.
This project's CI matrix and `pyproject.toml` both require **3.10** as
a floor (`.github/workflows/ci.yml` `python-version: ["3.10", "3.11",
"3.12"]`; `[tool.mypy] python_version = "3.10"`) — confirmed by direct
read, not assumed. Using `ExceptionGroup` would either silently break
3.10 or require a conditional-import shim, both worse than a small,
dependency-free custom exception type. This was caught during 20C's
adversarial review, not discovered after implementation.

### Public contract

Per this project's established convention, **every** exception class
lives in `errors.py`, regardless of which module raises it (confirmed
by direct read: `RegistryError` is defined in `errors.py` but raised
from `module.py`; `ExecutionError` likewise). `ListenerDeliveryError`
follows the same pattern — defined in `errors.py`, imported and raised
from `events.py`. My first draft of this ADR incorrectly placed it in
`events.py`; corrected here before implementation, not after.

```python
# errors.py


class ListenerDeliveryError(RAGTorchError):
    """One or more listeners raised during publish().

    Every listener that was subscribed at the start of publish() was
    still invoked -- a raising listener never prevents delivery to
    listeners after it (see ADR-023). `failures` holds every
    (listener, exception) pair, in delivery order. The original event
    is available as `event`.
    """

    def __init__(
        self,
        event: Event,
        failures: tuple[tuple[EventListener, Exception], ...],
    ) -> None:
        self.event = event
        self.failures = failures
        summary = ", ".join(
            f"{getattr(listener, '__name__', repr(listener))}: {type(exc).__name__}: {exc}"
            for listener, exc in failures
        )
        super().__init__(
            f"{len(failures)} listener(s) raised while publishing "
            f"{event.type.value} for '{event.module_name}': {summary}"
        )
```

```python
# events.py -- publish() gains a snapshot + isolate-and-continue loop;
# ListenerDeliveryError is imported from errors.py like every other
# exception raised in this file.


class EventBus:
    def publish(self, event: Event) -> None:
        """Deliver `event` to every subscribed listener.

        Every listener subscribed at the start of this call is
        invoked, even if an earlier listener raised (ADR-023) -- a
        snapshot of the listener list is taken before iteration
        begins, so mutation during delivery (subscribe/unsubscribe
        from within a listener) does not affect which listeners this
        call reaches; see Concurrency below for what this snapshot
        does and does not guarantee. If any listener raised,
        ListenerDeliveryError is raised after every listener has run,
        carrying every failure. If no listener raised, publish()
        returns normally, exactly as before.
        """
```

`EventScope.publish` gets the identical treatment — both classes
change symmetrically, matching how EVT-FAIL-001 was originally
recorded as affecting both.

### Why aggregate rather than first-failure-wins or log-only?

- **First-failure-wins** (today's accidental behavior, formally
  ratified) was rejected: it is the defect this ADR exists to fix —
  silent partial delivery with no signal to the caller that some
  listeners never ran.
- **Log-only, never raise** was rejected: it maximizes delivery
  robustness but makes a broken listener fail silently forever unless
  someone is actively watching logs — a real regression from today's
  at-least-fails-loudly (if incomplete) behavior. A caller who
  currently depends on `publish()` raising when a listener is broken
  would lose that signal entirely.
- **Isolate-and-continue, aggregate** was selected: no listener can
  block another's delivery (fixes the confirmed defect), and no
  failure is silently swallowed (`ListenerDeliveryError` still
  surfaces every failure to the caller) — the strictly better position
  on both axes, at the cost of a slightly larger public surface (one
  new exception type) and a small, benchmarked, per-listener
  try/except cost.

## Failure model

| Failure | Behavior |
|---|---|
| No listener raises | `publish()` returns normally, exactly as before this ADR |
| One listener raises | Every other listener still runs; `publish()` raises `ListenerDeliveryError` with one `(listener, exception)` pair |
| Multiple listeners raise | Every listener still runs; `publish()` raises `ListenerDeliveryError` with every failing pair, in delivery order |
| A listener raises `BaseException` that is not `Exception` (e.g. `KeyboardInterrupt`, `SystemExit`) | **Not caught** — only `Exception` and its subclasses are isolated; control-flow/interpreter-shutdown signals propagate immediately, interrupting delivery to remaining listeners. This is a deliberate, named exception to "every listener still runs," not an oversight. |
| Listener mutates the listener list during `publish()` (subscribe/unsubscribe from within a listener) | Snapshot semantics: `publish()` iterates a snapshot taken at the start of the call. A listener added during this `publish()` is not invoked by this same call (only by the next `publish()`); a listener removed during this `publish()` is still invoked by this call (its removal takes effect starting next call). This is a **behavior change** from today's live-iteration semantics (confirmed in 20C: today, an added listener may or may not be observed by the same call, and a removed listener is silently skipped mid-iteration) — replacing an accident with a specified, tested contract. |
| A listener calls `publish()` again on the same bus (reentrant `publish()`) | **Out of scope, but required an explicit fix to stay unchanged.** Reentrant `publish()` still causes unbounded recursion / `RecursionError` (confirmed in 20C), exactly as before this ADR. Naively applying `except Exception` around each listener would have caught the *recursive* `ListenerDeliveryError` too, producing a deeply nested chain of wrapped errors instead of one clean `RecursionError` propagating up — discovered during implementation verification, not the original 20C review. `publish()` therefore re-raises `RecursionError` immediately, before the generic isolation clause, restoring the original clean single-`RecursionError` behavior exactly. See Non-goals/EVT-REENTRANT-001. |

## Concurrency

Unchanged from ADR-022's own Concurrency section — this ADR does not
add, remove, or alter any synchronization guarantee:

- `EventScope` cross-execution isolation (Claim A) — unaffected,
  untouched by this change.
- `EventBus`/`EventScope` thread safety (Claim B) — **still not
  guaranteed**. The listener-list snapshot this ADR introduces
  (`list(self._listeners)` or equivalent at the start of `publish()`)
  is not a synchronization primitive — it protects against
  mutate-during-this-call side effects (20C finding #3), not against
  concurrent access from multiple threads. EVT-RACE-001 remains fully
  open, unchanged, and explicitly excluded from this ADR's scope (see
  Non-goals).

## Async compatibility

`publish()` remains a plain synchronous method; the isolate-and-continue
loop and the snapshot are both ordinary synchronous Python, no
different in async-compatibility terms than `publish()` already was.
Does not solve or block any future async execution path.

## Serialization

Not applicable. `ListenerDeliveryError` is a runtime-only exception
(like every other exception in `errors.py`); no new persistent state
is introduced.

## Security

`ListenerDeliveryError`'s message includes each failing listener's
`__name__` (or `repr()` if unavailable) and the string form of its
exception — the same class of information `Module.__call__`'s existing
`payload={"error": str(exc)}` already surfaces for `MODULE_FAILED`
events, not a new category of exposure. No event payload content is
added or changed by this ADR.

## Non-goals

Explicitly deferred, not part of this decision:

- **`EventBus`/`EventScope` thread safety (EVT-RACE-001).** Still
  fully open. This ADR's snapshot-before-iterating change is not a
  concurrency fix and must not be read as one — see Concurrency above.
- **Reentrant-`publish()` recursion safety.** A listener that calls
  `publish()` again on the same bus can still cause unbounded
  recursion (20C finding #4) — unrelated to *sibling*-listener
  isolation, not addressed here. `publish()` explicitly re-raises
  `RecursionError` before its generic isolation clause specifically
  *to preserve* this pre-existing, unaddressed behavior unchanged (see
  Failure model) — without that explicit re-raise, isolate-and-continue
  would have made this scenario's failure mode strictly worse (a
  deeply nested chain of `ListenerDeliveryError`s instead of one clean
  `RecursionError`), which would have been an unintended regression,
  not a neutral non-goal.
- **Non-`Exception` `BaseException` isolation** (e.g.
  `KeyboardInterrupt`). Deliberately not caught — see Failure model.
- **Changing which exceptions `Module.__call__` wraps as
  `ExecutionError`.** `Module.__call__`'s own exception handling around
  its `publish()` call sites is untouched by this ADR. **Precise
  behavior, empirically confirmed by direct execution against the
  actual implementation (not assumed — this ADR's own drafting got
  this wrong twice before checking empirically, corrected here rather
  than left as a plausible-sounding but false claim):** for all three
  event types (`MODULE_STARTED`, `MODULE_FINISHED`, `MODULE_FAILED`),
  a raising listener causes `ListenerDeliveryError` to propagate
  **raw and unwrapped** out of `Module.__call__` — it is never caught
  and re-wrapped as `ExecutionError`. This holds even for
  `MODULE_FAILED`'s publish calls, which are lexically inside the
  `except Exception as exc:` block that wraps the *original*
  `forward()` failure: that `except` clause only catches exceptions
  raised by the code in its corresponding `try:`, not exceptions
  raised by statements inside the `except` block's own body (ordinary
  Python control flow, not special-cased by this ADR). No
  special-casing for `ListenerDeliveryError` was added anywhere in
  `Module.__call__`, and none was needed — its existing structure
  already produces this uniform "always raw, never wrapped" result for
  every listener-failure scenario.
- **Fixing `Module.__call__`'s dual-publish sequencing.** `_bus.publish(event)`
  and `scope.publish(event)` remain two separate, sequential, unwrapped
  statements — a raising global-bus `publish()` call still prevents
  the scope's `publish()` call from ever running, exactly as before
  this ADR (see Compatibility for the full explanation and the
  regression test that pins this). This is ADR-022's contract, not
  this ADR's; a future ADR could independently wrap each call if a
  real requirement demands it.

## Alternatives considered

- **First-failure-wins, formally ratified as the contract.** Rejected
  — see Decision. Would ratify the exact silent-partial-delivery
  defect this ADR exists to close.
- **Log-only, never raise.** Rejected — see Decision. Regresses
  today's at-least-fails-loudly behavior.
- **Native `ExceptionGroup`.** Rejected — see Decision. Requires
  Python 3.11+, incompatible with this project's 3.10 floor.
- **Snapshot only for `EventScope`, leave `EventBus` unchanged.**
  Rejected — EVT-FAIL-001 was recorded as affecting both classes
  identically (20C confirmed this empirically, both classes share the
  identical hazard), and leaving `EventBus` with the old defect while
  fixing `EventScope` would be an inconsistent, confusing contract
  between two structurally-identical types.

## Testing strategy

- **FAIL-ISO-01** No listener raises: `publish()` returns normally,
  unchanged from today (regression test).
- **FAIL-ISO-02** One listener raises: every other listener still
  runs; `publish()` raises `ListenerDeliveryError` with exactly one
  failure recorded.
- **FAIL-ISO-03** Multiple listeners raise: every listener still runs;
  `ListenerDeliveryError.failures` contains every failing pair, in
  delivery order.
- **FAIL-ISO-04** A later listener's side effect (e.g. appending to a
  list) still happens even when an earlier listener raised — direct
  proof of "every listener still runs," not merely that the exception
  type changed.
- **FAIL-ISO-05** `BaseException` subclasses that are not `Exception`
  (e.g. a custom `BaseException` subclass, since `KeyboardInterrupt`
  itself is impractical to test directly) propagate immediately,
  are not caught, and stop delivery to subsequent listeners — pinning
  the deliberate exception to "every listener still runs."
- **FAIL-ISO-06** A listener that unsubscribes another listener during
  `publish()`: the unsubscribed listener still runs during *this*
  `publish()` call (snapshot semantics), confirmed different from
  today's skip-on-removal behavior (20C finding #3).
- **FAIL-ISO-07** A listener that subscribes a new listener during
  `publish()`: the newly-subscribed listener does **not** run during
  *this* `publish()` call, only on the next one (snapshot semantics).
- **FAIL-ISO-09** A listener that calls `publish()` again on the same
  bus (reentrant call) still raises a clean, unwrapped `RecursionError`
  that propagates immediately — not a nested chain of
  `ListenerDeliveryError`s. Direct regression test for the fix required
  during implementation verification (EVT-REENTRANT-001).
- **FAIL-ISO-08** `EventScope` gets the identical FAIL-ISO-01 through
  FAIL-ISO-07 coverage — both classes tested symmetrically, not just
  `EventBus`.
- **API-01 (extended)** `ListenerDeliveryError` appears in both
  `ragtorch.core.__all__` and `ragtorch.__all__`, importable both ways
  — matching the existing public API parity test pattern from Step 18.
- **COMPAT-01** Every pre-existing `test_events.py` test continues
  passing unmodified where its scenario has zero raising listeners
  (the overwhelming majority) — the observable-behavior change is
  scoped exactly to multi-listener-with-a-raising-listener scenarios.

## Benchmark strategy

`benchmarks/step20_listener_failure_isolation.py`. Two tiers:

1. **No-failure baseline vs. new implementation** — does the added
   try/except-per-listener and the listener-list snapshot cost
   anything measurable when nothing actually fails (the common case)?
2. **Failure-path cost** — with N listeners, M of which raise, what
   does isolate-and-continue cost relative to today's fail-fast
   short-circuit?

As with every prior benchmark in this project: measures, does not
prove, an overhead claim; no threshold assertion; not wired into CI
(matching the majority file-only precedent).

## Compatibility

**This is an intentional, user-visible behavior change** for the
narrow case of multi-listener delivery where at least one listener
raises — not merely additive, unlike ADR-022. Existing callers with
zero raising listeners (the overwhelming majority, confirmed by
`grep`-ing `test_events.py`'s existing tests — none subscribe a
raising listener alongside a non-raising one) see no behavior change.
Existing callers who *do* subscribe a raising listener today see
`RuntimeError`/whatever-they-raised replaced by
`ListenerDeliveryError` — a breaking change for that narrow case,
explicitly named here rather than silently introduced. `EventBus`,
`EventScope`, `Event`, `EventType`, `event_bus()` — all other behavior
unchanged.

**Named scope boundary, discovered during implementation
verification, not the original design:** this ADR's isolation
guarantee applies *within* one `EventBus.publish()`/`EventScope.publish()`
call. `Module.__call__`'s dual-publish (ADR-022) calls
`_bus.publish(event)` then, as a **separate, sequential, unwrapped
statement**, `scope.publish(event)`. If the global bus's `publish()`
call itself raises `ListenerDeliveryError` (because one of *its*
listeners failed), that exception propagates out of `Module.__call__`
immediately — the second statement (`scope.publish`) is never reached,
exactly as the old `RuntimeError` also prevented it before this ADR
(confirmed by test: `test_global_listener_failure_still_prevents_scope_delivery_through_module_call`).
**This ADR does not fix that cross-call sequencing** — doing so would
mean changing `Module.__call__` itself, which is ADR-022's contract,
not this one's; ADR-023 is scoped to `events.py` only (see Non-goals).
Calling `EventScope.publish()` directly, independent of
`Module.__call__`/the global bus, is fully isolated as designed
(`test_event_scope_itself_isolates_from_a_failing_global_bus_listener`).

## Dependencies

Zero new runtime dependencies. `ListenerDeliveryError` uses only
`RAGTorchError` (already imported pattern from `errors.py`) and
standard library `tuple`/`list`.

## Deferred risks

Carried forward, unchanged by this ADR:

- **EVT-RACE-001** — `EventBus`/`EventScope` thread safety. Still
  fully open; explicitly out of scope here (see Non-goals).

New, named by this ADR's own adversarial review (20C):

- **EVT-REENTRANT-001** — Reentrant `publish()` (a listener calling
  `publish()` again on the same bus) can cause unbounded recursion /
  `RecursionError`. Real, confirmed empirically (20C finding #4), not
  addressed by this ADR (isolate-and-continue only isolates sibling
  listeners within one call, not a listener re-entering `publish()`
  itself) — but implementing isolate-and-continue required an explicit
  `except RecursionError: raise` guard, placed before the generic
  isolation clause, specifically so this pre-existing, unaddressed
  failure mode did not become *worse* (nested `ListenerDeliveryError`
  wrapping instead of one clean `RecursionError`). This guard was
  discovered necessary during implementation verification, not the
  original 20C adversarial review — recorded here as a correction to
  that review's own coverage, not silently folded in as if it had been
  anticipated from the start. Deferred, formally recorded here so it
  does not become forgotten the way EVT-FAIL-001 might have without
  ADR-022's own Deferred Risks section.

## Acceptance criteria

- [ ] Contract (this ADR's Public contract section)
- [ ] Implementation (`events.py`)
- [ ] Unit tests (FAIL-ISO-01 through FAIL-ISO-08, API-01, COMPAT-01)
- [ ] Integration tests (through real `Module.__call__`/`Sequential`
      composition paths, proving `ListenerDeliveryError` propagates
      correctly through `Module.__call__`'s existing exception
      wrapping)
- [ ] Failure tests (covered by FAIL-ISO-* above)
- [ ] Benchmark (`benchmarks/step20_listener_failure_isolation.py`)
- [ ] Evaluation (`evaluation/step20-evaluation.md`)
- [ ] CI (PR + post-merge)
- [ ] Documentation (this ADR; requirements matrix row)
- [ ] Compatibility (reviewed above; breaking-change scope named)
- [ ] Security (reviewed above)
- [ ] Dependencies (reviewed above; zero new)
- [ ] Diff review
- [ ] Post-merge CI
