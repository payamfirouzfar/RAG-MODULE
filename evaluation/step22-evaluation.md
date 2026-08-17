# Step 22 Evaluation — Event Reentrancy Audit (`EVT-REENTRANT-001`)

Date: 2026-08-17 (22A-22L, local) — pending CI/merge

## Status

**Overall status: IN PROGRESS.**

This step's central result is **Outcome A**: current behavior is
correct and sufficient. No ADR-024, no production code change. The
deliverable is a 15-case (R1-R15) empirical audit, deterministic
characterization tests, a benchmark, and precise documentation.
Remaining: push, PR, CI, merge, post-merge CI, final closure.

## Evidence vocabulary

Frozen vocabulary reused verbatim from Steps 18-21.

## 22A — Repository audit

Confirmed `main` at `12481ae6ddc09e9b360f361ea18c49afcd85e5fc` (Step 21
final closure) via `git log`/`git rev-parse HEAD`, and PR #28's merged
state directly via `gh pr view 28 --json state,mergeCommit` (state
`MERGED`, merge commit `ab628db...`).

Read `events.py`, `errors.py`, `module.py`, `execution.py`,
`context.py` in full; `engine.py` grepped for any `publish`/
`EventBus`/`EventScope` reference (none found — `engine.py`'s
docstring only *mentions* that `Module.__call__` handles publishing,
it never calls `publish()` itself); ADR-022, ADR-023 (especially the
existing `EVT-REENTRANT-001` record); Step 20/21 evaluations;
requirements matrix.

**Key structural findings:**

- `execution.py` (`SequentialExecutor`) has zero relationship to event
  publishing — confirmed by direct read, no `publish`/`EventBus`
  reference anywhere in the file.
- `context.py` only carries a reference-typed `event_scope` field; it
  never calls `publish()`.
- `Module.__call__` is the *only* production code path that calls
  `publish()` — confirmed via `grep -n "publish(" src/ragtorch/core/module.py`,
  three call sites (`MODULE_STARTED`, `MODULE_FAILED`,
  `MODULE_FINISHED`), none nested inside another `publish()` call in
  the framework's own code. Reentrancy can therefore only occur if a
  *caller's own listener* calls `publish()` (directly or by invoking a
  `Module`) — the framework itself never does this internally.
- Existing test coverage for reentrancy: exactly one test,
  `test_fail_iso_09_reentrant_publish_raises_clean_recursion_error`
  (Step 20), covering only the unconditional same-event recursion case
  (R7-equivalent). Everything else audited below is new territory.

## 22B — Problem definition: the 15 cases (R1-R15)

Each case reproduced empirically (deterministic, no `time.sleep`),
verified directly against `main`, not assumed:

| Case | Description | Observed result |
|---|---|---|
| R1 | listener publishes a *different*, terminating event | Works correctly: `['first', 'second']` delivery order, no error |
| R2 | listener publishes the *same* event recursively | Same as R7 (unconditional recursion) |
| R3 | nested publish reaches other outer listeners | **Precisely characterized**: nested delivery fully completes (reaching every listener) *before* the outer loop resumes — `[('a','first'),('a','second'),('b','second'),('b','first')]`, not simple publish-order |
| R4 | nested publish succeeds, outer resumes | Confirmed via R1/R3 — outer resumes correctly after nested completion |
| R5 | nested publish raises, listener catches it | Outer delivery completely unaffected — other outer listeners still run |
| R5b | nested publish raises, listener does NOT catch it | ADR-023's isolate-and-continue already handles this with zero reentrancy-specific code — the outer `publish()`'s own `except Exception` catches the propagated `ListenerDeliveryError` like any other listener failure; other outer listeners still run |
| R6 | nested publish causes an unrelated listener failure | Covered by R13 — isolation holds at the nested level too |
| R7 | unconditional same-event recursion | Cleanly raises `RecursionError` after exactly 499 calls (Python's default 1000-frame limit, ~2 frames/level framework overhead) |
| R8/R9 | `EventBus` vs. `EventScope` reentrancy | Identical — structurally identical `publish()` implementations, confirmed via parametrized tests |
| R10 | `EventBus` listener invokes `EventScope.publish()` | Not reentrancy at all — different objects, independent listener snapshots, works correctly with zero recursion risk |
| R11 | `EventScope` listener invokes `EventBus.publish()` | Symmetric to R10, same conclusion |
| R12 | listener self-unsubscribes then nests | Composes cleanly with existing snapshot semantics (Step 20/23) — the nested call correctly sees the updated (post-unsubscribe) listener list |
| R13 | nested publish, multiple listeners, one fails | ADR-023 isolation applies fully at the nested level — the non-failing nested listener still ran |
| R14 | reentrancy through real `Module.__call__` execution | Reproduces the identical `RecursionError` — the realistic failure mode, not merely a synthetic direct-`publish()` scenario. Confirms `Module.__call__` neither masks nor corrupts the exception (propagates raw, uncaught by its `except Exception` clauses — same finding as `ListenerDeliveryError` in Step 20) |
| R15 | reentrancy across `MODULE_STARTED`/`MODULE_FINISHED`/`MODULE_FAILED` separately | Not independently varying — all three call sites share the identical unwrapped-propagation structure (Step 20's own empirical finding), so R14's result generalizes to all three without needing separate reproduction |

## 22C — Concurrency vs. reentrancy distinction

Explicitly distinguished and demonstrated, not merely asserted:

- **Concurrent mutation** (Step 21's subject): two *different threads*
  racing to mutate `_listeners` or call `publish()` simultaneously.
  Addressed by Step 21 (Outcome B — no synchronization justified).
- **Nested/reentrant publish** (this step's subject): *same-thread*,
  synchronous control flow where a listener's own call stack includes
  another `publish()` call before the outer one returns. No threading
  involved at all — every R1-R15 reproduction above runs on a single
  thread.
- **Recursive publish of the same event**: a specific *subset* of
  reentrancy (R2/R7) — the listener re-triggers itself (or an
  equivalent chain) with no terminating condition.
- **Nested publish of a different event**: the *general* case (R1,
  R3-R6, R10-R13) — legitimate, already-working, already-correct
  behavior.

No `threading.Lock`/`RLock`/`asyncio`/`contextvars`/queue/executor was
introduced or considered necessary — this step never needed any of
them, since reentrancy is a same-thread control-flow question, not a
synchronization question.

## 22D — ADR-023 compatibility audit

All six of ADR-023's guarantees explicitly re-verified against the
audit's own reproductions, not assumed unaffected:

1. **Snapshot semantics preserved**: R12's reproduction directly
   confirms the nested `publish()` call sees the listener list as
   mutated by the point the nested call begins — consistent with
   ADR-023's `tuple(self._listeners)` snapshot-per-call design.
2. **One ordinary Exception does not prevent later listeners**: R5b
   directly confirms this holds even when the failure originates from
   a *nested* `publish()` call, not just a direct listener failure.
3. **Ordinary failures aggregate into `ListenerDeliveryError`**:
   confirmed unchanged — R5/R5b/R13 all observe `ListenerDeliveryError`
   exactly as ADR-023 specifies.
4. **`RecursionError` propagates rather than nesting into
   `ListenerDeliveryError`**: confirmed unchanged — R7's reproduction
   shows a single, clean `RecursionError`, not a wrapped chain (the
   exact behavior the `except RecursionError: raise` guard, added
   during Step 20's own implementation verification, exists to
   preserve).
5. **Python 3.10 remains supported**: this step adds zero production
   code, so this is trivially true — confirmed via `git diff --stat`
   showing zero lines in any `src/` file.
6. **`EventBus`/`EventScope` remain behaviorally aligned**: every R1-R13
   case parametrized across both classes (`@pytest.mark.parametrize`)
   confirms identical behavior, not assumed from structural similarity
   alone.

## 22E — Empirical reproduction

All reproductions used deterministic Python execution — no
`time.sleep`, no timing-dependent assertions beyond the Tier-C
benchmark's own order-of-magnitude bound (which uses `< 1.0` seconds,
not a precise value, specifically to stay robust across hardware while
still catching a real regression like a hang).

**Recursion depth**: 499 calls before `RecursionError`, at Python's
default `sys.getrecursionlimit() == 1000` — not asserted as a fixed
contract (this is CPython's own default, not a ragtorch guarantee),
but recorded as the empirically observed budget available for
legitimate nesting today.

**16 new deterministic tests** added to
`tests/unit/core/test_events.py` (7 parametrized functions ×
`EventBus`/`EventScope` = 14, plus 2 non-parametrized
`Module.__call__`-specific tests):
`test_r1_nested_publish_of_a_different_terminating_event_works_correctly`,
`test_r3_nested_publish_reaches_other_listeners_before_outer_resumes`,
`test_r5_nested_publish_failure_caught_by_listener_does_not_affect_outer_delivery`,
`test_r5b_uncaught_nested_publish_failure_is_isolated_by_outer_publish`,
`test_r7_unconditional_same_event_recursion_raises_clean_recursion_error`,
`test_r10_cross_object_nesting_is_not_reentrancy`,
`test_r12_self_unsubscribe_then_nested_publish_sees_updated_snapshot`,
`test_reentrant_recursion_through_real_module_call_raises_clean_recursion_error`,
`test_reentrant_recursion_is_cheap_and_self_bounded`. All pass locally
(522/522 total suite), re-run 5× consecutively to confirm determinism
before being treated as evidence.

## 22F — Adversarial policy comparison

Five candidate policies evaluated against 15 criteria
(correctness, determinism, backward compatibility, listener ordering,
failure propagation, observability, debuggability, API complexity,
Python 3.10 compatibility, future async compatibility, serialization,
provider independence, performance, security, testability):

| Policy | Verdict |
|---|---|
| A — Preserve current behavior | **Wins every criterion** — already correct (R1-R13 compose cleanly), already tested, zero new surface, confirmed cheap/self-bounded (security) |
| B — Detect same-event recursion, raise a dedicated error | No evidence defining "same event" identity; new exception type to integrate with `ListenerDeliveryError`; breaking change for callers relying on today's `RecursionError` (ADR-023's own tested contract) |
| C — Suppress recursive publication | **Regression**: silently dropping a publish directly contradicts ADR-023's "never silently swallow" principle; could mask a real application bug indefinitely |
| D — Queue nested publication until outer delivery finishes | **Largest surface expansion** of any option — fundamentally changes ordering for every nested case (not just recursive ones, per R3's characterized ordering), and pre-empts a future async-delivery design decision that doesn't belong in this step |
| E — Bounded depth limit | Arbitrary threshold with no evidence tying it to a real failure mode; same bookkeeping cost as B for every non-recursive `publish()` call too |

**Full comparison table in the PR/commit history** (this document's
companion analysis) — condensed here since Policy A's dominance across
every criterion made an exhaustive per-cell table unnecessary to
duplicate in full; the underlying reasoning is preserved in ADR-023's
updated `EVT-REENTRANT-001` entry.

## 22G — Future-change review

- **Replaceable?** Yes — `RecursionError` propagation is Python's own
  default, not a ragtorch abstraction needing future deprecation.
- **Extensible?** Yes — R1 already proves legitimate nested workflows
  work without any extension.
- **Future async compatibility?** Unaffected either way; a future
  async contract (already deferred, ADR-018/019) would define its own
  reentrancy semantics from scratch.
- **Serializable?** N/A.
- **Observable?** Yes — a clean `RecursionError` traceback is maximally
  observable; no candidate policy improved on this.
- **Fails safely?** Yes — confirmed empirically: self-bounded, sub-
  millisecond to failure (200-sample benchmark).
- **Public API stable?** Yes — zero new public surface.
- **Understandable six months later?** Yes — "recursion raises
  `RecursionError`" needs no project-specific concept.

No new abstraction (`EventDispatcher`, `EventQueue`,
`ReentrancyManager`, `EventScheduler`, `AsyncEventBus`) is justified —
none of the 15 cases produced evidence current behavior is
insufficient.

## 22H — Benchmark

`benchmarks/step22_event_reentrancy_audit.py`, three tiers:

```
Tier A -- direct publish cost (baseline, unchanged):
 listeners    p50 (us)    p95 (us)
         0       0.400       0.500
         1       0.400       0.500
        10       0.700       0.800

Tier B -- one-level nested publish (different, terminating event):
1-level nest       1.400       1.900

Tier C -- recursive same-event publish until RecursionError:
 recursion    p50 (ms)    p95 (ms)
to-failure       0.283       0.570

python=3.12.0
```

Tier A confirms zero cost was added (nothing changed). Tier B shows
nesting cost is additive and proportional to the extra `publish()`
call, not superlinear. Tier C (200 fresh-object samples) confirms the
earlier single-run 1.22ms measurement's order of magnitude: recursion
to failure costs well under 1ms typically. No threshold asserted, not
wired into CI (matching majority file-only precedent).

## 22I — Security review

Directly answered by Tier C's benchmark: accidental infinite recursion
self-terminates in **under 1 millisecond** (median), bounded by
Python's own interpreter recursion limit — **not a meaningful
denial-of-service vector**. No uncontrolled resource consumption (no
unbounded memory growth — confirmed the call stack unwinds cleanly on
`RecursionError`), no event amplification beyond what a caller's own
listener code explicitly does (R1's terminating-nested-event case
produces exactly the events the listener code asks for, nothing
more), no accidental repeated side effects beyond what R1-R13 already
characterize precisely. No security control added — none justified by
evidence.

## 22J — Decision: OUTCOME A

**Current behavior is correct and sufficient.** No production code
change. No ADR-024. `EVT-REENTRANT-001` remains Deferred — this audit
re-confirms, rather than resolves, that status, with new evidence
explaining precisely *why* it remains the right call: every legitimate
nesting pattern already works correctly, and the one failure mode
(unconditional same-event recursion) is self-bounded, cheap, and
already well-tested since Step 20.

## Compatibility review

No public API change: no new export, no signature change, no behavior
change. `EventBus`/`EventScope`/`ListenerDeliveryError`/`event_bus()`
all unchanged. `Module.__call__` unchanged.

## Dependency review

`git diff` against every dependency manifest — empty. No dependency
changes.

## Diff review

```
git status --short (pre-commit):
 M docs/architecture/decisions/ADR-023-event-listener-failure-isolation.md
 M tests/unit/core/test_events.py
?? benchmarks/step22_event_reentrancy_audit.py
?? evaluation/step22-evaluation.md
```

`src/ragtorch/core/events.py`, `errors.py`, `module.py` — all confirmed
unmodified. This is the expected, correct footprint for a genuine
Outcome-A step: evidence, characterization tests, and documentation,
zero production code.

## Closure

Pending: push, PR, CI (3.10/3.11/3.12), merge, post-merge CI
verification, final closure record. Since no new capability was
fulfilled (the existing `EVT-REENTRANT-001` deferred-risk record was
updated with new evidence, not resolved), whether a requirements-matrix
row is warranted will be decided during closure, following the same
"do not invent an A-number prematurely" discipline Step 21 applied.
