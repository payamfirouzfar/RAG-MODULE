# Step 21 Evaluation — Event Concurrency Audit (EVT-RACE-001 / EVT-REENTRANT-001)

Date: 2026-08-17 (21A-21K, local) — pending CI/merge

## Status

**Overall status: IN PROGRESS.**

This step's central result is **Outcome B**: the audit does not
support implementing synchronization. No ADR-024, no production code
change. The deliverable is deterministic characterization evidence and
precise documentation. Remaining: push, PR, CI, merge, post-merge CI,
final closure.

## Evidence vocabulary

Frozen vocabulary reused verbatim from Steps 18-20.

## 21A — Repository audit

Read `events.py`, `errors.py`, `module.py`, `execution.py`,
`context.py`, `block.py`, `sequential.py`, `engine.py` in full;
`EventBus`/`EventScope` tests; ADR-021, ADR-022, ADR-023; Step 18/20
evaluations; requirements matrix; `.github/workflows/ci.yml`;
`pyproject.toml`.

**Answers to the 15 audit questions, each evidence-backed:**

1. **Does the core currently promise thread safety?** No — confirmed
   by direct `grep` across `docs/`/`README.md`: every mention of
   "thread-safe"/"thread safety" is an explicit non-guarantee
   statement (ADR-018, ADR-020, ADR-022, ADR-023), never a promise.
2. **Does any supported runtime path actually publish concurrently?**
   No — `grep -Rn "threading|ThreadPoolExecutor|concurrent.futures|asyncio" src/ragtorch/`
   returns zero real imports (only the English word "threading" in
   docstrings describing data flow, e.g. "threading prior results
   forward"). `ExecutionEngine`, `Executor`, `SequentialExecutor`,
   `Module.__call__` are all single-threaded, synchronous code paths.
3. **Can `EventBus` be shared between executions?** Yes, by design —
   it is the single global `_bus` instance (ADR-022's whole point is
   giving callers an *alternative*, `EventScope`, precisely because
   the global bus is always shared).
4. **Can `EventScope` be shared between executions?** Yes, if a caller
   chooses to (ADR-022 Q8) — not automatic.
5. **Are listeners mutated during active publication?** Only if a
   caller's own listener code does so — no framework code path does
   this. Step 20's snapshot already isolates each `publish()` call
   from such mutation.
6. **Is listener registration expected to happen concurrently?** No
   evidence found — no test, no documented use case, no existing
   caller pattern in this repository relies on concurrent
   subscribe/unsubscribe.
7. **Is publication expected concurrently?** Only in the sense that a
   caller *could* run multiple threads each calling `Module.__call__`
   independently — but the library itself never does this internally.
8. **Is the same `EventBus` intentionally global?** Yes — `_bus`,
   confirmed in `module.py`, is deliberately one process-wide
   singleton (ADR-003's original design, reaffirmed by ADR-022 Q2).
9. **Does execution use threads anywhere?** No — confirmed by the
   `grep` in point 2.
10. **Does the library expose a concurrent API?** No — no `async def`,
    no thread pool, no queue-based dispatch anywhere in `src/ragtorch`.
11. **Do tests already assume concurrent use?** Only the deliberate,
    deterministic `threading.Barrier`-based tests from Steps 18/20,
    which exist specifically to *characterize* current behavior under
    concurrency, not to exercise a supported concurrent API.
12. **Does documentation promise concurrent safety?** No — see point 1.
13. **Is concurrent use currently undefined behavior?** Precisely
    characterized as *unguaranteed but empirically well-behaved for
    memory safety*, not "undefined" in the C sense — see 21B/21C's
    empirical findings below.
14. **Does Python 3.10 constrain the possible design?** Yes, directly
    relevant if synchronization were pursued: `pyproject.toml`
    `[tool.mypy] python_version = "3.10"` and
    `.github/workflows/ci.yml` `python-version: ["3.10", "3.11", "3.12"]`
    are both confirmed hard floors (same fact ADR-023 already used to
    reject `ExceptionGroup`).
15. **Would synchronization introduce lock-order/deadlock concerns?**
    Moot — no synchronization was added (see 21D below), so this
    question was never reached in practice; the adversarial-review
    checklist items about it are recorded as N/A, not silently
    skipped.

## 21B — Evidence table (deterministic reproductions)

All reproductions used `threading.Barrier`, never `time.sleep`, and
were re-run multiple times to confirm determinism, not one-off luck.

| Candidate | Evidence | Current behavior | Consequence | Architectural impact | Recommendation |
|---|---|---|---|---|---|
| A. Concurrent subscribe/unsubscribe | 2×1000-iteration concurrent subscribe, zero crashes, correct final count (2000) | GIL-protected | None | None | No action |
| B. Concurrent publish | 4×500 concurrent publishes = 2000/2000 delivered, no loss | Correct delivery count | None | None | No action |
| C. Publish while listener list mutates | 20,000-iteration aggressive churn (subscribe+unsubscribe+publish simultaneously), zero crashes | Step 20's snapshot already isolates each call | None | None — already addressed by Step 20 | No action |
| D. Concurrent `EventScope` mutation | 3-way concurrent subscribe+publish, 5000 iterations/thread, zero crashes | Same as `EventBus` (structurally identical) | None | None | No action |
| E. Same listener registered concurrently | Covered by A | `subscribe()` never dedupes, single- or multi-threaded | Pre-existing, not concurrency-specific | None | No action |
| F. Reentrant publish | Already addressed by Step 20 (`EVT-REENTRANT-001`) | Unchanged, deliberately preserved | Documented non-goal | None | No new action |
| G. Listener publishes another event | Same as F if same bus; no new hazard for independent buses | Correct | Covered by F | None | No action |
| H. Listener subscribes/unsubscribes itself | **Concurrent double-`unsubscribe()` of the same listener deterministically races to `ValueError`** in the losing thread (reproduced 5/5 runs) | **Pre-existing, single-threaded**: confirmed `unsubscribe()` on an already-removed listener already raises `ValueError` with zero threads | A caller doing concurrent idempotent-style unsubscribe could hit an undocumented `ValueError` | Real, narrow documentation gap — not a code defect | **Document, don't lock** |
| I. Nested `EventScope` | N/A — `EventScope` has no nesting concept; `child()` propagates the same object (ADR-022) | N/A | N/A | N/A | No action |
| J. Concurrent independent execution contexts | Already `EVT-ISOLATION-001` (Step 18), proven structurally + empirically | Proven, CI-tested | None | None | No action — already solved |

## 21C — Adversarial review

The pre-registered 15-item adversarial checklist (deadlock, lock
inversion, reentrant lock requirements, callback-under-lock hazards,
listener calling subscribe/unsubscribe/publish, long-running
listeners, snapshot consistency, event ordering, duplicate delivery,
starvation, lock contention, global `EventBus` contention) is **N/A in
its entirety** — none of these apply, because no synchronization
primitive is being introduced. There is nothing to deadlock, no lock
held during a callback, no lock-order to invert. This is recorded
explicitly rather than silently skipped, per the instruction's own
rule against silent omission.

**Conclusion**: the only real finding (H) is not a concurrency-specific
defect at all — it is the same pre-existing, single-threaded
"`unsubscribe()` is not idempotent" contract question, made reachable
non-deterministically by concurrency rather than newly created by it.

## 21D — ADR decision

**No ADR-024.** The audit does not support implementing
synchronization — matching `SequentialExecutor`'s own existing
precedent (ADR-018): *"Thread-safety, reentrancy, and concurrent
invocation of the same instance are separate, untested contracts not
claimed here."* Recording this decision here, per the instruction's
explicit guidance not to create an ADR "merely for the sake of having
one."

## 21E-21J — Contract, implementation, tests, integration, failure, benchmark

**No production code changed** (`events.py`, `errors.py`, `module.py`
all confirmed unmodified via `git diff --stat` — zero lines). The
deliverable is:

- **Tests (21G)**: 10 new tests in `tests/unit/core/test_events.py`
  (5 parametrized functions × `EventBus`/`EventScope`):
  `test_concurrent_subscribe_does_not_corrupt_or_lose_registrations`,
  `test_concurrent_publish_delivers_every_event_no_loss_no_duplication`,
  `test_concurrent_subscribe_and_publish_does_not_crash`,
  `test_concurrent_unsubscribe_of_the_same_listener_can_race_to_valueerror`,
  `test_double_unsubscribe_already_raises_single_threaded`. All
  deterministic (`threading.Barrier`), all pass locally (506/506 total
  suite). A pre-existing gap from Step 20 was also fixed incidentally:
  `test_listener_delivery_error_importable_from_core_and_root` was
  missing its `CoreLDE` assertion (present in source but never
  executed) — found and fixed while editing this exact area.
- **Integration (21H)**: not applicable — no new production behavior
  exists to exercise through composition paths; the existing 18G
  concurrent-composition test (`test_global_bus_current_concurrent_delivery_behavior_on_cpython`)
  already covers this territory and needed no change.
- **Failure/edge cases (21I)**: covered by the H-finding tests above
  (both the concurrent race and its single-threaded root cause are
  pinned as tests, not just prose).
- **Benchmark (21J)**: `benchmarks/step21_event_concurrency_audit.py`,
  two tiers:

```
Tier A -- single-threaded publish cost (baseline, unchanged since Step 20):
 listeners    p50 (us)    p95 (us)
         1       0.400       0.500
        10       0.600       0.700
       100       3.500       7.400
      1000      24.600      32.200

Tier B -- concurrent publish cost (fixed 10 listeners, N worker threads):
   workers   total publishes   wall time (s)    us/publish
         1              5000          0.0042        0.8472
         2             10000          0.0059        0.5887
         4             20000          0.0116        0.5812
         8             40000          0.0245        0.6114

python=3.12.0
```

Tier A confirms no cost was added (matches Step 20's shape exactly,
since nothing changed). Tier B shows per-publish cost actually
decreasing slightly then plateauing as worker count increases —
consistent with fixed per-thread overhead amortizing across more
parallel throughput under the GIL, not evidence of pathological
contention. No threshold asserted, not wired into CI (matching the
majority file-only precedent).

## 21K — Documentation

`docs/architecture/decisions/ADR-022-execution-scoped-event-delivery.md`'s
`EVT-RACE-001` entry updated in place with the Step 21 audit findings
(deterministic reproductions, the double-unsubscribe finding and its
single-threaded root cause, the five new characterization tests) —
the existing deferred-risk record remains the authoritative home for
this information rather than creating a parallel document.

## 21N — Compatibility review

No public API change: no new export, no signature change, no behavior
change. `EventBus`/`EventScope`/`ListenerDeliveryError`/`event_bus()`
all unchanged.

## 21O — Security review

No new findings. Concurrent double-unsubscribe raising `ValueError` is
an availability/correctness question for a caller doing something
unusual, not a security exposure — no data crosses a trust boundary,
no new information is disclosed.

## 21P — Dependency review

`git diff` against every dependency manifest — empty. No dependency
changes.

## 21Q — Diff review

```
git status --short (pre-commit):
 M tests/unit/core/test_events.py
?? benchmarks/step21_event_concurrency_audit.py
?? docs/architecture/decisions/ADR-022-execution-scoped-event-delivery.md (modified)
?? evaluation/step21-evaluation.md
```

`src/ragtorch/core/events.py`, `errors.py`, `module.py` — all
confirmed unmodified. This is the expected, correct footprint for an
Outcome-B step: evidence and documentation, zero production code.

## Deferred risks (unchanged, re-confirmed by this audit)

- `EVT-RACE-001` — still open, re-audited, decision unchanged (no
  synchronization). See updated ADR-022 entry.
- `EVT-REENTRANT-001` — still open, unaffected by this step (Step 20's
  fix remains correct and unchanged).
- **New, narrow finding** (not a formally-numbered risk — too small to
  warrant one, per this project's discipline against inflating the
  risk registry): `unsubscribe()` is not idempotent, single- or
  multi-threaded. No evidence justifies changing this; documented and
  tested, not fixed.

## Closure

Pending: push, PR, CI (3.10/3.11/3.12), merge, post-merge CI
verification, final closure record. Since no ADR-024 and no A-numbered
requirements-matrix row is warranted (no new requirement was
fulfilled — the existing `EVT-RACE-001` deferred-risk record was
updated, not resolved), documentation closure for this step consists
of the ADR-022 update already made above, not a new matrix row.
