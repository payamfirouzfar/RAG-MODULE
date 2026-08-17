# Step 20 Evaluation — Event Listener Failure Isolation

Date: 2026-08-17 (20A-20Q, local) — pending CI/merge

## Status

**Overall status: IN PROGRESS.**

Local implementation, tests, benchmark, and evaluation are done.
Remaining: push, PR, CI, merge, post-merge CI, documentation closure
(A72), following the identical discipline Steps 18/19 established.

## Evidence vocabulary

Frozen vocabulary reused verbatim from Steps 18/19 (Planned / Audited /
Designed / Contract-frozen / Implemented / Test-proven /
Benchmark-proven / Locally verified / CI-proven / Deferred / Blocked /
Accepted / Complete).

## 20A — Repository audit

Audited `main` at `dd019c6` directly, not from the historical "Next
priority" list, which was confirmed stale (items #1-#4 already closed
by Steps 15/16/18/19). Read `docs/architecture/requirements-matrix-v0.1.md`,
`v0.1-architecture.md`, ADR-015 through ADR-022 (especially ADR-022's
Deferred Risks), `src/ragtorch/core/events.py` in full, `.github/workflows/ci.yml`
(confirming the 3.10 Python floor — directly relevant to a later
design decision), and `pyproject.toml`'s `[tool.mypy] python_version`
line (also 3.10).

**Candidate table:**

| Candidate | Existing support | Concrete evidence | Value | Risk | Compat impact | Benchmark need | Recommendation |
|---|---|---|---|---|---|---|---|
| A. `EventBus`/`EventScope` listener-failure isolation (EVT-FAIL-001) | Both classes exist, unmodified since Step 18 | **Empirically confirmed** (not assumed from ADR-022's prose): a raising listener silently prevents delivery to every subsequently-subscribed listener — reproduced directly against `main` | High — real defect class (silent partial delivery) | Medium — requires an explicit failure policy | Requires care — user-visible change for a narrow case | Yes | **Selected** |
| B. `EventBus` concurrency synchronization (EVT-RACE-001) | Same | Confirmed a real, unspecified behavior exists, but EVT-RACE-001's own record says "revisit when a real requirement... demands it" — no new evidence beyond the risk's own pre-existing text | Medium | High — genuinely architectural | High if careless | Yes | **Excluded** — no new evidence |
| C. `CompositionGraph` incremental validation | — | Still no real workload evidence (Step 12's own evaluation defers this) | Low | Low | None if untouched | N/A | **Excluded** — unchanged since Step 18A/19A |
| D. Serialization/reproducibility | — | No concrete consumer | — | — | — | — | **Excluded** |
| E. Async/parallel execution | — | `ExecutionPlan` already preserves this without action | — | — | — | — | **Excluded** — speculative |
| F. Provider integration | — | Zero provider implementations exist | — | — | — | — | **Excluded** — nothing to integrate |

## 20B — Selection

Candidate A, listener-failure isolation. Direction (isolate-and-continue
vs. log-only vs. formally-ratify-first-failure-wins) confirmed via
explicit user decision before design work began — deliberately not
pre-selected by the audit itself, per the instruction package.

## 20C — Adversarial review

Findings, each empirically reproduced against `main`/the in-progress
implementation, not assumed:

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | Native `ExceptionGroup` (PEP 654) requires Python 3.11+; CI/`pyproject.toml` both require 3.10 as a floor | BLOCKER for the originally-considered mechanism | Fixed before implementation: custom `ListenerDeliveryError`, not `ExceptionGroup` |
| 2 | Concurrent subscribe-during-publish is observed by the in-flight iteration (reproduced) | Real, pre-existing, unrelated to failure isolation | Frozen as an explicit non-goal (EVT-RACE-001 territory) |
| 3 | Listener removal during publish silently skips the next listener (reproduced — classic mutate-during-iterate bug) | Real, directly relevant | Fixed as a named consequence: snapshot-before-iterating |
| 4 | Reentrant publish causes unbounded recursion / `RecursionError` (reproduced) | Real, pre-existing, out of scope for *sibling*-isolation | Frozen as an explicit non-goal, EVT-REENTRANT-001 |
| 5 | `EventScope` shares every hazard identically | Confirms fix must be symmetric | Applied to both classes |
| 6-13 | Duplicate delivery, ordering, global/scoped interaction, nested composition, provider dependency, serialization/async hazards, hidden state, mutation-after-failure | Checked, none found relevant beyond what's already tracked | No new finding |

**Post-implementation discoveries (beyond the original 20C pass, corrected in place rather than hidden):**

- Naive `except Exception` per listener would have caught the
  *recursive* `ListenerDeliveryError` on reentrant publish, nesting
  once per recursive level and destroying the clean `RecursionError`
  finding #4 was supposed to leave unchanged — a real regression
  discovered during implementation verification, not the original
  review. Fixed with an explicit `except RecursionError: raise` guard
  before the generic isolation clause, applied to **both** `EventBus`
  and `EventScope` (an initial fix only touched `EventBus`, caught by
  the FAIL-ISO-09 parametrized test failing for `EventScope`).
- `Module.__call__`'s exact exception-wrapping behavior for
  `ListenerDeliveryError` was claimed incorrectly **twice** during this
  ADR's own drafting before being verified empirically: the correct,
  confirmed-by-direct-execution finding is that all three event types
  (`MODULE_STARTED`, `MODULE_FINISHED`, `MODULE_FAILED`) let
  `ListenerDeliveryError` propagate raw, never wrapped as
  `ExecutionError` — including `MODULE_FAILED`, whose publish calls
  sit lexically inside an `except Exception as exc:` block but are not
  thereby caught by it (ordinary Python: an `except` clause only
  catches exceptions from its own `try:`, not from its own body). Both
  incorrect claims were corrected in ADR-023 and pinned by direct
  regression tests before this document was written, not left as
  plausible-sounding assumptions.

## 20D — ADR decision

**ADR-023 required** — this changes failure semantics (a real,
user-visible behavior change for a narrow case), unlike Step 19's
cycle detection. Status: Proposed (moves to Accepted only after
post-merge CI, per Step 18/19's established precedent).

## 20E — Public contract (frozen)

```text
EventBus.publish(event) / EventScope.publish(event):
  - takes a snapshot of _listeners before iterating
  - invokes every listener in the snapshot, even if an earlier one raised
  - RecursionError from any listener re-raises immediately, unwrapped
    (EVT-REENTRANT-001 unchanged)
  - any other Exception is isolated per-listener
  - non-Exception BaseException (KeyboardInterrupt, SystemExit) is NOT
    caught -- propagates immediately, stops delivery to remaining listeners
  - if >=1 listener raised an Exception: raises ListenerDeliveryError
    (event, failures) after every listener has run
  - if no listener raised: returns normally, unchanged from before

ListenerDeliveryError(RAGTorchError):
  .event -- the Event being published
  .failures -- tuple[(listener, exception), ...] in delivery order
```

## 20F — Implementation

- `src/ragtorch/core/errors.py` — new `ListenerDeliveryError`
  (`TYPE_CHECKING`-only import of `Event`/`EventListener` from
  `events.py` to avoid a runtime circular import, matching how
  `context.py` already does the same for `EventScope`).
- `src/ragtorch/core/events.py` — `EventBus.publish`/`EventScope.publish`
  both rewritten: snapshot (`tuple(self._listeners)`), per-listener
  try/except with an explicit `RecursionError` re-raise guard, and
  `ListenerDeliveryError` raised at the end if any failures occurred.
- `src/ragtorch/core/__init__.py`, `src/ragtorch/__init__.py` —
  `ListenerDeliveryError` added to both `__all__` lists.
- `tests/unit/test_public_api.py` — also added `EventScope` (a
  pre-existing Step 18 gap, fixed incidentally while touching this
  file for `ListenerDeliveryError`) and `ListenerDeliveryError` to the
  expected-exports set.

`Module.__call__` (`module.py`) is **unmodified** — confirmed by
`git diff --stat` showing zero changes to that file.

## 20G — Unit tests

`tests/unit/core/test_events.py`:

- 3 pre-existing tests (18D/18E's EVT-FAILSTOP contract) rewritten
  in place to reflect the new, intentionally-changed behavior:
  `test_global_listener_failure_still_prevents_scope_delivery_through_module_call`
  (renamed and corrected — see 20K's Compatibility note),
  `test_scope_listener_failure_raises_listener_delivery_error`,
  `test_event_scope_isolates_listener_exceptions`.
- 1 new test added to isolate the claim precisely:
  `test_event_scope_itself_isolates_from_a_failing_global_bus_listener`.
- 12 new parametrized tests (`@pytest.mark.parametrize("bus_cls",
  [EventBus, EventScope])`), covering FAIL-ISO-01 through FAIL-ISO-09
  from ADR-023's Testing strategy (each parametrization counts as a
  separate collected test, so 6 parametrized functions × 2 classes =
  12): no-failure baseline, one/multiple listeners raising, later
  listeners' side effects still happen, non-`Exception`
  `BaseException` not caught, removal-during-publish still runs,
  subscribe-during-publish doesn't run yet (snapshot semantics),
  reentrant publish still raises clean `RecursionError`.
- 1 new API parity test:
  `test_listener_delivery_error_importable_from_core_and_root`.

Total: 496 tests passing locally (up from 474 at Step 19's close).

## 20H — Integration tests

`tests/integration/test_execution_scoped_events.py`, 4 new tests
through real `Module.__call__`/`Sequential` composition paths:

- `test_failing_listener_on_module_started_propagates_unwrapped`
- `test_failing_listener_on_module_finished_propagates_unwrapped`
- `test_failing_listener_on_module_failed_also_propagates_unwrapped`
  (the empirically-corrected claim — see 20C)
- `test_listener_failure_isolation_through_sequential_composition`
  (proves isolate-and-continue holds through real `Sequential`
  execution, not just isolated `EventBus`/`EventScope` unit calls)

## 20I — Failure/edge-case tests

Covered by FAIL-ISO-01 through FAIL-ISO-09 (20G) and the four
integration tests (20H) — no separate section needed, the contract
*is* a failure-behavior contract.

## 20J — Benchmark

`benchmarks/step20_listener_failure_isolation.py`, two tiers per
ADR-023's Benchmark strategy:

```
Tier 1 -- no-failure baseline:
 listeners    p50 (us)    p95 (us)
         1       0.500       1.200
        10       0.700       0.800
       100       3.000       4.100

Tier 2 -- failure-path cost (all listeners raise):
 listeners    p50 (us)    p95 (us)
         1       2.300       2.900
        10       8.600      65.500
       100      93.500     372.800

python=3.12.0
```

No surprise: no-failure baseline stays cheap and scales roughly
linearly; the failure path costs more per listener (exception
construction/handling), also roughly linear, with wider p95 spread at
higher counts (allocation/GC variance). No threshold asserted, not
wired into CI (matching the 12+/14 majority file-only precedent from
Step 18's 18H-1/18H-2 audit).

## 20K — Compatibility review

**Intentional, user-visible breaking change**, explicitly named, not
silently introduced: any existing caller subscribing a raising
listener alongside other listeners now sees `ListenerDeliveryError`
instead of the raw listener exception, and every listener runs instead
of only those before the first failure. Confirmed via `grep` that no
existing pre-Step-20 test relied on the old short-circuit behavior in
a way that wasn't itself the test *of* that behavior (all three such
tests were the EVT-FAILSTOP tests, intentionally rewritten — see 20G).

**Named scope boundary** (not a defect, a precise fact): `Module.__call__`'s
dual-publish (`_bus.publish(event)` then `scope.publish(event)`,
ADR-022) remains two separate, sequential, unwrapped statements. A
raising global-bus listener still prevents the scope's `publish()`
call from running at all — the *within-one-publish-call* isolation
this ADR provides does not extend across those two separate calls.
Pinned by
`test_global_listener_failure_still_prevents_scope_delivery_through_module_call`.
Fixing this would be an ADR-022 change, explicitly out of this
step's scope.

## 20L — Security review

`ListenerDeliveryError`'s message includes each failing listener's
`__name__`/`repr()` and its exception's string form — the same class
of information `Module.__call__`'s existing `payload={"error": str(exc)}`
already surfaces, not a new exposure category. No event payload
content added or changed.

## 20M — Dependency review

`git diff` against `pyproject.toml`/`requirements.txt`/`setup.py`/
`setup.cfg` — empty. Zero new runtime dependencies; `ListenerDeliveryError`
uses only `RAGTorchError` and standard library `tuple`.

## 20N — Diff review

```
git status --short (pre-commit):
 M src/ragtorch/__init__.py
 M src/ragtorch/core/__init__.py
 M src/ragtorch/core/errors.py
 M src/ragtorch/core/events.py
 M tests/integration/test_execution_scoped_events.py
 M tests/unit/core/test_events.py
 M tests/unit/test_public_api.py
?? benchmarks/step20_listener_failure_isolation.py
?? docs/architecture/decisions/ADR-023-event-listener-failure-isolation.md
```

`module.py`, `context.py`, `sequential.py`, `block.py`, `engine.py` —
all unmodified. `tests/unit/test_public_api.py`'s incidental fix
(adding the pre-existing, Step-18-era missing `EventScope` entry) is
the one line in this diff not strictly required by Step 20's own
contract — kept because it was directly adjacent (same file, same
line group, same underlying cause: an exception/type added to
`__init__.py` without updating this parity test) rather than a
separate, unrelated cleanup.

## Closure

Pending: 20L (post-merge CI verification, not yet run), 20M
(documentation — ADR-023 → Accepted, requirements matrix A72),
following the identical sequence Steps 18/19 established.
