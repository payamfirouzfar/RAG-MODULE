# Step 18 Evaluation — Execution-Scoped Event Delivery

Date: 2026-08-17 (18A) — updated through 18H + real CI evidence (PR #25)

## Status

**Overall status: IN PROGRESS.**

Step 18 is not complete until 18A–18L have independently satisfied:
repository audit, architecture/design, ADR, contract, implementation,
unit tests, integration/contract tests, failure/edge-case tests,
benchmark, evaluation, CI, documentation, compatibility, security,
dependency review, and final diff/release gate. This document is the
Step 18 evidence ledger — the durable record of what has actually been
proven, and by what evidence, as opposed to what ADR-022 architecturally
decided. ADR-022 remains authoritative for architectural reasoning
(decision, alternatives, non-goals, deferred risks); this document
mirrors that ADR's status against actual test/benchmark/CI evidence and
tracks it per-gate rather than as one aggregate claim.

**18A–18H are now CI-proven, not merely locally verified.** PR #25
(`feat/step18-event-scoped-delivery-audit` → `main`) triggered a real
`pull_request`-scoped run of `.github/workflows/ci.yml`
(run `32035631246`): `test (3.10)`, `test (3.11)`, `test (3.12)` all
green, every configured step passed, including the newly-added Step 18
benchmark step. This is genuine CI execution — a downloaded artifact
from the actual run, not a re-typed local result. See the 18J row in
the Evidence Matrix and the "18J (pulled forward)" subsection under
18H for the full record. **18I (final synthesis), 18K (docs/
compatibility/security/dependency), and 18L (release gate) remain
open** — Step 18 as a whole is still IN PROGRESS.

## Evidence vocabulary

Every status cell in the tables below uses exactly one of these terms,
deliberately, to prevent "verified" from becoming an ambiguous catch-all:

| Term | Meaning |
|---|---|
| Planned | Identified as needed; not yet started |
| Audited | Repository/source inspected directly; no design decision yet |
| Designed | A design exists (may be pre-ADR) |
| Contract-frozen | A frozen public contract exists (tests written against it) |
| Implemented | Production code exists satisfying the frozen contract |
| Test-proven | An automated test demonstrates the claim, run locally |
| Benchmark-proven | A benchmark demonstrates a measured characteristic |
| Locally verified | A command was run in this repository and its output inspected |
| CI-proven | The claim is established by the repository's actual CI run, not a local command |
| Deferred | A real, known gap — intentionally not fixed in this step, with a formal record |
| Blocked | Cannot proceed without a decision/input not yet available |
| Accepted | Formally reviewed and approved (e.g. an ADR's Accepted status) |
| Complete | Every required gate for the item has reached its terminal proof state |

**Local vs. CI is never collapsed.** "461 passed" below means *local
test-proven*; it does not mean CI-proven until an actual `.github/workflows/ci.yml`
run confirms it (18J). No claim in this document says "Step 18 is
production-ready" — that status is invalid until the 18L release gate
is reached.

## Event-system identifier registry

One risk/requirement → one stable ID, frozen here and reused
everywhere (this ledger, ADR-022, test names/docstrings) rather than
re-derived per mention:

| ID | Meaning |
|---|---|
| `EVT-ISOLATION-001` | `EventScope` cross-execution isolation (ADR-022 Concurrency §, Claim A) |
| `EVT-FAILURE-001` | Failure reaches the owning execution's scope |
| `EVT-FAILURE-002` | Failure in one execution does not affect a sibling execution |
| `EVT-RACE-001` | Global `EventBus` synchronization / thread-safety (deferred risk — ADR-022) |
| `EVT-FAIL-001` | Listener-failure isolation, `EventBus` and `EventScope` (deferred risk — ADR-022) |

`EVT-RACE-001` and `EVT-FAIL-001` originate in ADR-022 and are kept
verbatim here, not renamed, per the one-ID-per-risk rule. The EVT-*
labels used inside `tests/unit/core/test_events.py`'s docstrings
(`EVT-01`, `EVT-NOCTX-01`, `EVT-CHILD`, etc., from the 18D contract
freeze) are test-case labels, a separate, narrower namespace scoped to
that file's own contract enumeration — not requirement/risk IDs, and
not renamed here either.

## Step 18 Evidence Matrix (18A–18L)

| Step | Area | Requirement / Question | Contract source | Evidence | Local | CI | Status |
|---|---|---|---|---|---|---|---|
| 18A | Audit | Next highest-value gap identified from requirements/architecture, not intuition | requirements-matrix A5/A10, architecture §5 | this document (Gaps 1-4, ranking table) | ✓ | N/A | Audited |
| 18B | Audit | Execution lifecycle (`ExecutionContext`/`Run`/`Event`/`EventBus`/`ExecutionEngine`) understood from source, not assumed | `step18b-source-audit.md` | full-file reads + empirical `Sequential` construction | ✓ | N/A | Audited |
| 18B | Audit | 12 decision-gate questions answered with source citations | `step18b-source-audit.md` | Q1-Q12 answers | ✓ | N/A | Audited |
| 18C | Architecture/ADR | Event delivery scoping mechanism explicitly decided | ADR-022 | ADR-022 Decision, Alternatives considered | ✓ | N/A | Designed |
| 18C | ADR | ADR-022 drafted, addressing all 12 decision-gate questions | ADR-022 | ADR-022 full document | ✓ | N/A | Designed (Status: Proposed, not yet Accepted) |
| 18D | Contract | ADR-022 contract frozen into executable tests before implementation | ADR-022 | `tests/unit/core/test_events.py` (EVT-*), pre-implementation collection failure confirmed | ✓ | N/A | Contract-frozen |
| 18E | Implementation | `EventScope`, `ExecutionContext.event_scope`, `child()` propagation, `Module.__call__` dual delivery | ADR-022 Decision | `events.py`, `context.py`, `module.py`, `__init__.py` exports | ✓ | ✓ (PR #25, run 32035631246) | **Implemented, CI-proven** |
| 18E | Test | Focused EVT-* contract tests pass against implementation | ADR-022 | `test_events.py`, 22 passed | ✓ | ✓ (part of "Unit and integration tests" step, all 3 Python versions) | **Test-proven, CI-proven** |
| 18E | Test | Full suite regresses cleanly | — | 461 passed (final count including 18F/18G/18H additions) | ✓ | ✓ (all 3 Python versions) | **Test-proven, CI-proven** |
| 18E | Quality | Lint/format clean | — | `ruff check`/`ruff format --check` | ✓ | ✓ ("Check formatting"/"Lint" steps, all 3 Python versions) | **CI-proven** |
| 18E | Quality | `mypy`, scoped exactly as CI runs it (`files = ["src/ragtorch"]`) | `pyproject.toml` `[tool.mypy]` | `mypy` bare invocation, 0 errors | ✓ | ✓ ("Type check" step, all 3 Python versions) | **CI-proven** |
| 18F | Integration | Real composition paths (`Sequential`, nested `Sequential`, `Block`, `RAGModule`, `ExecutionEngine`) propagate `event_scope` | ADR-022 | `test_execution_scoped_events.py`, 9 tests (18F) | ✓ | ✓ (part of full suite CI run) | **Test-proven, CI-proven** |
| 18F | Integration | No production architecture change required to satisfy the contract | — | `git diff --stat` shows zero changes to `sequential.py`/`block.py`/`engine.py` | ✓ | N/A | Verified |
| 18F | Compatibility | Global bus remains independent of scoping | ADR-022 Q2 | `test_global_bus_remains_independent_of_execution_scope` | ✓ | ✓ (part of full suite CI run) | **Test-proven, CI-proven** |
| 18G | Concurrency | `EVT-ISOLATION-001` — Claim A: `EventScope` cross-execution isolation | ADR-022 Concurrency §, Claim A | `test_concurrent_executions_do_not_cross_event_scopes`, `test_concurrent_executions_stay_isolated_across_repeated_runs` (20 iterations) | ✓ | ✓ (ran on GitHub-hosted Ubuntu runners, all 3 Python versions, not just local Windows) | **Test-proven, CI-proven** (structural + empirical) |
| 18G | Concurrency | Claim B — `EventBus` thread safety | ADR-022 Concurrency §, Claim B | `test_global_bus_current_concurrent_delivery_behavior_on_cpython` — deliberately NOT framed as proof | — | — | **Not guaranteed** (see Deferred Risks, `EVT-RACE-001`) — CI running this test does not change this claim; the test itself asserts no guarantee |
| 18G | Failure | `EVT-FAILURE-001` — failure reaches owning execution scope | ADR-022 | `test_failure_events_reach_execution_scope` (18F) | ✓ | ✓ (part of full suite CI run) | **Test-proven, CI-proven** |
| 18G | Failure | `EVT-FAILURE-002` — failure in one execution does not affect a sibling execution | ADR-022 | `test_failure_in_one_execution_does_not_affect_a_sibling_execution` | ✓ | ✓ (part of full suite CI run) | **Test-proven, CI-proven** |
| 18G | Quality | Full suite / lint / format / diff-check after 18G additions | — | 461 passed, clean lint/format, clean diff-check | ✓ | ✓ (all 3 Python versions) | **CI-proven** |
| 18G | Quality | B023 late-binding closure defects caught and fixed in test code itself | — | lint output diffed before/after fix | ✓ | N/A | Test-proven (defect in test authoring, not production code) |
| 18H | Benchmark | Event delivery overhead measured (no scope / empty scope / active scope), corrected baseline (`context=None`, not `ExecutionContext()`) | ADR-022 Benchmark strategy | `benchmarks/step18_execution_scoped_events.py`; 3 local corrected runs (18H-C1) + real CI artifact from PR #25 run 32035631246 (Python 3.12.13: no_scope p50 4.318µs, empty/active ~5.0µs, +16% scope-check delta) | ✓ | ✓ (benchmark executed successfully and artifact uploaded on all 3 Python versions) | **Benchmark-proven, CI-proven** |
| 18I | Evaluation | Step 18 behavior evaluated against the frozen ADR-022 contract as a whole, every claim traced to evidence | this document | 18I-1 through 18I-20 above, including an explicit provenance table and an unsupported-claims check | ✓ | N/A (docs-only synthesis; no new executable claim requiring CI) | **Locally verified (synthesis complete)** |
| 18J | CI | Required CI gates pass on the repository's actual CI workflow, not a local approximation | `.github/workflows/ci.yml` | PR #25, run 32035631246 — `test (3.10)`, `test (3.11)`, `test (3.12)` all green, every configured step passed | ✓ | ✓ | **CI-proven** |
| 18K | Docs | ADR-022 status moved to Accepted; requirements matrix A5/A10 evidence columns updated | requirements-matrix-v0.1.md | pending | pending | pending | Planned |
| 18K | Compatibility | Full compatibility review recorded (API/behavioral/serialization/runtime) | — | pending | pending | pending | Planned |
| 18K | Security | Full security review recorded (event payload exposure, cross-execution observability) | ADR-022 Security § (preliminary) | pending expanded review | pending | pending | Planned |
| 18K | Dependencies | Dependency review recorded (expect: zero new dependencies) | ADR-022 Dependency review § | pending confirmation pass | pending | pending | Planned |
| 18L | Release | Final diff/status/release gate | — | pending | pending | pending | Planned |

## Deferred Risks (mirrored from ADR-022; ADR-022 remains authoritative)

| ID | Risk | Current behavior | Guarantee | Status | Owner | Revisit trigger |
|---|---|---|---|---|---|---|
| EVT-RACE-001 | Global `EventBus` synchronization | Shared, unsynchronized listener `list`; no lock around subscribe/unsubscribe/publish | No thread-safety guarantee | Deferred | Unassigned | A real requirement demands `EventBus` concurrency guarantees (e.g. async/parallel execution support) |
| EVT-FAIL-001 | Listener-failure isolation (`EventBus` and `EventScope`) | A raising listener's exception propagates out of `publish()` unmodified | No sibling-listener isolation guarantee | Deferred | Unassigned | `EventBus`/`EventScope` becomes a reliability boundary a caller depends on |

## Objective

Determine the next highest-value missing capability in RAG-MODULE from
the repository's own requirements matrix, architecture document, and
evaluation history — not invented, not chosen by intuition. This
document is the audit deliverable; it does not implement anything.

## Current baseline

`main` at `160cc7a` (Step 17 complete, ADR-021 Accepted, A69
CI-proven). Verified directly, not assumed:

```
git status --short --branch: ## main...origin/main (clean, up to date)
ruff check .:           All checks passed
ruff format --check .:  134 files already formatted
mypy:                   Success: no issues found in 27 source files
pytest -q:               431 passed
```

No `TODO`/`FIXME`/`TBD` markers exist anywhere in `docs`, `evaluation`,
`src`, or `tests` (confirmed by grep; all incidental matches were
unrelated words like "depending," "incomplete" in a variable/test
name, or `RunStatus.PENDING`, not actual open markers).

## Requirements reviewed

Full `docs/architecture/requirements-matrix-v0.1.md` read in full (all
90 rows, R1-R15 and A1-A69, plus the per-step status narratives through
Step 13 and the "Next priority" section).

## Existing architecture reviewed

Full `docs/architecture/v0.1-architecture.md` read (all 14 sections),
with particular attention to §5 "Execution identity" and §6
"Observability contract," since these directly name invariants not
obviously satisfied by the current implementation.

## Existing implementation reviewed

`src/ragtorch/core/events.py` (full file) and its usage sites across
`module.py` — the concrete implementation behind A5/A10's stated gap.

## Existing tests reviewed

`tests/unit/core/test_events.py` (existing `EventBus`/`Event` test
coverage) to confirm what is and is not already tested for the
candidate gap.

## Existing evaluations reviewed

`evaluation/step14-evaluation.md` through `evaluation/step17-evaluation.md`
scanned for any of their own stated "next priority" items — none
exist; only the requirements matrix's own "Next priority" section
(written after Step 13, never updated since) has this content.

## Gaps discovered

### Gap 1 — Stale "Next priority" section in the requirements matrix

The matrix's own `## Next priority` section (line 365) was written
after Step 13 and never updated. Of its 6 items:

- #2 ("Design a `Block` type") — **done** (Step 16, ADR-020).
- #3 ("Design an executor that consumes `ExecutionPlan`") — **done**
  (Steps 14-15, ADR-018/019).
- #1 ("Add concurrency tests around event identity before moving
  event delivery to execution-scoped ownership") — **not done**.
  Never addressed by any of Steps 14-17.
- #4 (cycle-registration gap, A29's named limitation) — not done, not
  addressed.
- #5 (incremental graph validation, A61's named limitation) — not
  done, not addressed.
- #6 (process discipline reminder) — not a feature, ongoing.

This is not itself the gap to fix (a stale doc section isn't a
requirement), but it is the strongest textual evidence pointing at
which *requirement* is actually next in line, since items #2 and #3 —
once genuinely next — are now done, and #1 was never picked up in
their place.

### Gap 2 — `EventBus` is a process-wide global singleton, not
execution-scoped (A5, A10)

Confirmed by direct inspection of `events.py` and `module.py`:
`_bus = EventBus()` is a single module-level global
(`src/ragtorch/core/module.py:25`), shared by *every* `Module`
instance in the process, with no per-`Run`/per-`ExecutionContext`
isolation. `EventBus.publish` iterates one shared `_listeners: list`
for every event, from every execution, regardless of which `Run` it
belongs to.

Requirement A5: *"Explicit execution identity | ExecutionContext +
execution-scoped Events | **EventBus must eventually become
execution-scoped for isolation** | event identity tests + future
concurrency tests."* Requirement A10: *"No global mutable execution
state | explicit context + no global current-context mechanism |
**process-wide EventBus remains as compatibility delivery
mechanism** | future execution-scoped delivery tests."* Both rows have
stood open, describing the same gap, since Step 4 (five steps before
the matrix's own current end).

Architecture doc §5 (Execution identity) explicitly requires: *"Every
nested execution must preserve: root run identity; parent-child
relationship; immutable metadata; **sibling isolation**."* §6
(Observability contract) states events already carry `run_id`/
`parent_run_id` (confirmed in `Event`'s dataclass fields) — that part
of the gap the section itself names ("the event payload presently
identifies only a module name") is **already fixed** (Step 4). What
remains unfixed is *delivery*: a listener subscribed for one `Run`
currently receives events from every other concurrent or unrelated
`Run` too, because there is exactly one shared `EventBus` instance,
not one per execution.

**Why this matters more now than when A5/A10 were written**: Steps
16-17 built `Block` and `RAGModule.from_graph`, both of which can be
nested arbitrarily (`Block` containing `Block`, `RAGModule` wrapping
`Block` wrapping `Block`) and can appear as siblings inside the same
`CompositionGraph`/`Sequential`. A real consumer subscribing to
observe one architecture's events today has no way to filter out
events from a sibling or nested architecture running concurrently (or
even sequentially, if the listener is long-lived) — the isolation
architecture §5 requires does not hold at the delivery layer, only at
the identity layer.

### Gap 3 — A16's automated-enforcement gap (minor, not selected)

*"Component conformance checks never occur on a hot execution path...
enforcement is currently a documented rule + code review, not an
automated lint/architecture-test."* Real, but lower-value than Gap 2:
it is a regression-prevention mechanism for an already-satisfied
invariant, not a missing capability. Noted as a candidate, not
selected — see ranking below.

### Gap 4 — A61's incremental-validation gap (minor, not selected)

`CompositionGraph`'s functional updates (`add_node`, etc.) re-validate
the entire graph on every call rather than incrementally checking only
the delta. Explicitly named as an accepted tradeoff in
`evaluation/step12-evaluation.md`, not a defect — deferred "once a
real workload demonstrates it matters." No such workload exists yet.
Not selected: no evidence-based trigger to act on it now, and acting
without one would violate this project's own "measure before
optimizing" discipline (used repeatedly, e.g. ADR-018 Q11, ADR-020
Q11).

## Candidate next steps

| Candidate | Value | Risk | Complexity | Dependencies |
|---|---:|---:|---:|---:|
| Execution-scoped `EventBus`/event delivery (Gap 2, A5/A10) | High | Medium | Medium | `ExecutionContext`, `Module.__call__`, `ExecutionEngine` |
| Automated hot-path `Component`-check lint/test (Gap 3, A16) | Low | Low | Low | none |
| Incremental `CompositionGraph` validation (Gap 4, A61) | Low | Medium | Medium | `CompositionGraph` |
| Provider routing/fallback (A6/A7) | High | High | High | no provider yet exists to route between — premature |
| `Module.validate()` convenience method (A29's named deferral) | Low | Low | Low | `validate_snapshot()` |

## Selected Step 18

**Execution-scoped event delivery — closing A5/A10's gap.**

## Why this is the correct next step

1. **Directly named by two still-open requirements** (A5, A10) and an
   explicit architecture-doc invariant (§5 "sibling isolation") — not
   invented.
2. **The matrix's own stale "Next priority" list's only unaddressed
   feature item** (#1) from the point items #2/#3 were both
   completed.
3. **Unlocks correctness for concurrent/nested execution**, which
   Steps 16-17 just made structurally possible (`Block`-in-`Block`,
   `RAGModule.from_graph` results as siblings in a graph) — the
   isolation gap is more consequential now than when first named,
   since there was no nesting/composition to isolate before Step 16.
4. **Bounded, well-scoped, single-primitive** — consistent with this
   project's established "one primitive per step" discipline (Steps
   6-9's own explicit pattern): scope this to *event delivery
   isolation*, not a broader observability redesign (no OpenTelemetry
   export, no nested trace spans, no per-component metrics — all
   explicitly out of scope per architecture doc §6's own deferral).
5. **Testable without a provider**: like every prior step, this can be
   fully verified with fake components and no network/LLM dependency.

The other real candidates (Gap 3, Gap 4) are legitimate but strictly
lower-value: both are internal-quality improvements to already-correct
behavior, not a missing capability a real caller would need. A6/A7
(provider routing) are explicitly premature — there is no real
provider integration yet for a router to route between, and designing
one now would be exactly the "freeze speculative behavior" anti-pattern
this project has consistently avoided (ADR-018 Q12/Q13, ADR-020 Q6,
ADR-021 Q3).

## Acceptance criteria (preliminary — to be frozen in an ADR before implementation)

- Each `Run`/`ExecutionContext` gets event delivery isolated from
  sibling/unrelated runs — a listener subscribed against one
  execution's scope does not receive events from a concurrently or
  sequentially unrelated execution.
- `Module.__call__`'s existing, unmodified event-publishing call sites
  and `Event`'s existing fields (including `run_id`/`parent_run_id`)
  are preserved — no change to what an event contains, only to how
  subscription/delivery is scoped.
- The existing global `event_bus()` compatibility function and
  `EventBus` class remain available and working for callers that don't
  need scoping (backward compatibility, matching every prior step's
  discipline) — this is additive, not a breaking migration.
- No new runtime dependency, no async requirement, no OpenTelemetry
  export, no per-component metrics, no nested trace spans.

## Risks

- **Backward compatibility**: `event_bus()` and the module-level `_bus`
  singleton are already public API (`ragtorch.core.__all__` includes
  `event_bus`) — any change must not break existing subscribers using
  the global bus today.
- **Where does execution-scoped delivery actually plug in?** `Module.__call__`
  currently always publishes to the single global `_bus`. Making
  delivery execution-scoped requires either (a) `ExecutionContext`
  gaining a way to carry/reference a scoped bus, or (b) `ExecutionEngine`
  owning per-`Run` delivery and `Module.__call__` needing a way to
  reach it. This is a real architectural decision this evaluation does
  not resolve — it belongs in an ADR (ADR-022), not decided here.
- **Concurrency test infrastructure**: the matrix's own item #1 says
  "concurrency tests," implying this repository may not yet have a
  standard pattern for testing concurrent execution (threads,
  `asyncio`, or otherwise) — this needs its own investigation as part
  of the next audit phase (16B-style source audit), not assumed.

## Compatibility considerations

To be resolved in ADR-022: whether the existing `event_bus()`/`_bus`
global remains the default when no execution scope is requested (very
likely, per this project's additive-only precedent), and whether
`Module.__call__`'s publish call sites change signature or behavior in
any observable way (should not, if the scoping mechanism is threaded
through `ExecutionContext` rather than changed at the call site).

## Security considerations

Event payloads already avoid leaking arbitrary instance state (no
`vars()`/`__dict__` reads anywhere in the codebase's event-publishing
paths, consistent with `ArchitectureSnapshot`'s A28 guarantee). Scoped
delivery does not change what data an event carries — only which
listeners receive it — so no new data-exposure surface is anticipated,
but this must be explicitly re-verified once a design exists.

## Dependency considerations

Standard library only expected (`threading`/`contextvars` are the most
likely candidates for scoping delivery without a new dependency,
matching this project's zero-new-runtime-dependency record across all
17 prior steps) — to be confirmed during design, not assumed.

## Test strategy

Deferred to the next phase (source/design audit) — not designed here,
per this project's own discipline of not writing a test matrix before
a frozen contract exists.

## Benchmark strategy

Deferred to the next phase. Likely relevant: publish/subscribe
overhead per event, before and after scoping, matching every prior
step's "measure the actual boundary cost" pattern (e.g. ADR-018's
context-copying benchmark, ADR-020's per-call `Block` overhead
benchmark).

## CI strategy

No change to the existing CI ladder (ruff/format/mypy/pytest on
3.10/3.11/3.12) is anticipated. Any concurrency test must not become
flaky — a real risk specific to this candidate that prior steps
haven't had to manage, worth flagging now rather than discovering
during implementation.

## Documentation strategy

Requirements matrix A5/A10 evidence columns updated only after real
implementation/CI evidence exists (not now) — this document is the
audit record, not the completion record.

## Definition of Done — 18A audit phase (superseded by the Evidence Matrix above for 18B onward)

- [x] Repository baseline confirmed clean and fully verified (431/431,
  lint/format/mypy clean).
- [x] Requirements matrix read in full; every open-gap row identified.
- [x] Architecture document read in full; §5/§6 invariants checked
  against actual implementation, not assumed satisfied.
- [x] `events.py`/`module.py` inspected directly to confirm the gap is
  real, not merely textually present in a stale doc.
- [x] Candidates ranked; one selected with explicit reasoning, not
  chosen by intuition.
- [x] Explicitly declined the tempting-but-premature candidate
  (provider routing) with reasoning tied to this project's own
  established "don't freeze speculative behavior" discipline.
- [x] Source-level design audit (18B) — complete, see
  `step18b-source-audit.md`.
- [x] ADR-022 drafted (18C), tightened per review (delivery ordering
  non-contract, failure short-circuit precision, capability-vs-
  guarantee wording for Q8, `is`-identity for `child()`, shared
  `EventListener` type, CI strategy section) — Status: Proposed.
- [x] No implementation, no tests, no benchmark, no code changes of
  any kind were made during the 18A audit phase itself — confirmed:
  `git status` was clean at both the start and end of that phase
  except for this new evaluation file.

## 18H — Benchmark

### 18H-1/18H-2: repository and benchmark-convention audit

Inspected all 13 existing files under `benchmarks/` and
`.github/workflows/ci.yml` directly before writing any code. Finding:
**only `benchmarks/step5_event_context_overhead.py` is actually wired
into CI** (as a non-blocking `tee` + `upload-artifact` step,
`.github/workflows/ci.yml` lines 47-54). Steps 10 through 17's
benchmarks (12 of 13 existing files) exist as runnable, documented
files but are never referenced anywhere in `ci.yml`. This is a real
precedent split, not an oversight — the majority precedent (12 of 13)
is "file only, no CI wiring," which this step follows (decision
confirmed explicitly rather than assumed).

### 18H-3 through 18H-7: frozen benchmark design

- **Performance question:** does execution-scoped event delivery
  introduce material overhead relative to synchronous `Module.__call__`
  execution without it? (Not: "`publish()` must run below X µs" — no
  SLA is being established.)
- **Baseline:** `context=None` — the exact, unmodified pre-ADR-022
  path (`Module.__call__`'s context-free branch). See 18H-C1 below
  for a correction made to the implementation after this design was
  first frozen.
- **Workload — three tiers**, matching ADR-022's Benchmark strategy
  section exactly: (1) no scope, (2) empty `EventScope` (0 listeners),
  (3) active `EventScope` (1 listener) — isolating the
  `context.event_scope is not None` check-and-empty-publish cost (tier
  2 vs. 1) from actual listener-invocation cost (tier 3 vs. 2).
- **Repetitions/statistics:** 50,000 samples/tier, `perf_counter_ns`,
  p50/p95, 1,000-iteration warmup across all three tiers before timing
  — matching `step5_event_context_overhead.py`'s established convention
  exactly, since this benchmark measures the same subsystem.
- **Environment:** reported inline via `sys.version` (Python 3.12.0 in
  this run); OS/CPU not hard-coded, matching Steps 5/17's convention.

### 18H-8/18H-9: implementation and execution (original — superseded, see 18H-C1)

`benchmarks/step18_execution_scoped_events.py` was first written with
tier 1 constructed as `ExecutionContext()` (an already-context-aware
`ExecutionContext` instance with `event_scope=None`), not literal
`context=None`. Run three times (50,000 samples/tier each run):

| Run | no_scope p50 (µs) | empty_scope p50 (µs) | active_scope p50 (µs) | scope-check Δ% | delivery Δ% | total Δ% |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 2.500 | 2.600 | 2.500 | +4.00% | −3.85% | 0.00% |
| 2 | 2.400 | 3.000 | 2.600 | +25.00% | −13.33% | +8.33% |
| 3 | 2.300 | 2.400 | 2.600 | +4.35% | +8.33% | +13.04% |

**These three runs are historical and are not used as final
quantitative evidence.** The benchmark's own docstring described tier
1 as "`context=None` — today's exact, unmodified path," but the
implementation actually measured `module(1, context=ExecutionContext())`
— a different code path (`Module.__call__`'s context-*aware* branch
with `event_scope=None`, not its context-*free* branch). This
documentation/code mismatch was caught on review before 18I began and
is corrected in 18H-C1 below, per this project's standing rule that a
benchmark's description and its implementation must agree, not merely
resemble each other.

### 18H-C1: baseline correction

`no_scope_context = ExecutionContext()` / `module(1, context=no_scope_context)`
replaced with the literal, unconditional baseline: `module(1, context=None)`
for both the warmup loop and the `measure()` call. `empty_scope`/
`active_scope` tiers were already correct and are unchanged. The
benchmark's module docstring was also corrected to state the tier 1
contract explicitly and warn against the same mistake recurring.

### 18H-C1 (continued): corrected implementation and execution

Re-run three times (50,000 samples/tier each run) after the fix, on
the same interpreter (Python 3.12.0):

| Run | no_scope p50 (µs) | empty_scope p50 (µs) | active_scope p50 (µs) | scope-check Δ% | delivery Δ% | total Δ% |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 2.200 | 2.500 | 2.500 | +13.64% | 0.00% | +13.64% |
| 2 | 2.000 | 2.500 | 2.600 | +25.00% | +4.00% | +30.00% |
| 3 | 2.000 | 3.300 | 2.500 | +65.00% | −24.24% | +25.00% |

### 18H-10: interpretation (corrected)

**With the real `context=None` baseline, `no_scope` reads consistently
lower than both scoped tiers across all three runs** (2.0–2.2 µs for
`no_scope` vs. 2.5–3.3 µs for `empty_scope`/`active_scope`) — unlike
the pre-correction data, where tier 1 (itself already context-aware)
sat inside the same noise band as the other two tiers and produced
sign-flipping deltas. The scope-check overhead (tier 2 vs. tier 1) is
now **positive in all three runs** (+13.64%, +25.00%, +65.00%) — a
directionally consistent signal, though the magnitude still varies
substantially run to run (13.64% to 65.00%), indicating the absolute
effect size (roughly 0.3–1.3 µs at this sample size) is real but small
relative to interpreter/scheduling noise, not that it doesn't exist.

The listener-delivery overhead (tier 3 vs. tier 2) remains noisy and
sign-flipping (0.00%, +4.00%, −24.24%) — consistent with the
`EventScope.publish` loop body (one function call to a no-op lambda)
being cheap enough, relative to `ExecutionContext`/`Event`
construction cost already paid in tier 2, that this benchmark's
resolution cannot reliably separate it from noise.

**Correct conclusion, stated at the same precision the evidence
supports:** constructing an `ExecutionContext` with a non-`None`
`event_scope` (tiers 2/3) costs measurably more than the `context=None`
path (tier 1) — a real, small, sub-microsecond effect, directionally
consistent across all three corrected runs. The specific additional
cost of *listener delivery itself* (tier 3 vs. tier 2), as opposed to
the cost of merely carrying a non-`None` `event_scope` through
`ExecutionContext`/`Module.__call__`, is **not resolvable** from this
benchmark's current methodology and is not claimed. Neither is a
percentage figure — the *relative* deltas vary 5x across three runs
(13.64% to 65.00%) at essentially fixed *absolute* magnitude, meaning
the percentage swings are an artifact of the tiny denominator
(no_scope's ~2 µs), not a meaningfully varying effect; no percentage
number from this data should be quoted as characteristic.

This is reported at exactly this level of precision — no stronger, no
weaker — following the "evidence cannot be stronger than its weakest
provenance" rule: **Benchmark-proven** claim is "tiers 2/3 cost more
than tier 1, directionally, on this interpreter, at this sample size,"
not "execution-scoped delivery has negligible overhead" and not "event
delivery costs approximately N%."

### 18H-11/18H-12: artifact and threshold decision

Artifact: `benchmarks/step18_execution_scoped_events.py` itself (no
separate `evaluation/artifacts/` file — matching Steps 5/13-17's
convention of the benchmark file being its own artifact, run on
demand, rather than committing point-in-time numeric snapshots).
**No threshold is established** — consistent with every prior
benchmark in this project.

### 18H-C2: benchmark test-coverage audit

Checked whether this repository has any existing convention of
testing benchmark files (`grep -Rln "benchmarks" tests/` and
`grep -Rn "import benchmarks|from benchmarks" tests/`): **zero
matches** — no benchmark file, across all 13 in `benchmarks/`, is
imported or exercised by anything under `tests/`. No such convention
exists to extend. Per this project's standing rule against inventing a
new test framework for one step, **no benchmark-import test was
added**. The production behavior the benchmark exercises
(`Module.__call__` under `context=None` / `ExecutionContext(event_scope=None)`
/ `ExecutionContext(event_scope=<scope>)`) is already fully covered by
the existing 22 unit + 13 integration EVT-* tests (18D-18G) — the
benchmark itself remains focused on measurement only, per the
production-behavior/measurement/CI-smoke boundary already established.

### 18H-C3: CI decision (reversed from the original 18H-13)

**Original decision** (18H-13, superseded): follow the majority (12 of
13) file-only precedent, do not wire into CI.

**Reversed per explicit review**: this project's newer, stronger
completion rule ("every step must have test and CI evidence before it
is considered completely true — local proof is not CI proof") overrides
the earlier majority-precedent reasoning. `.github/workflows/ci.yml`
now runs `benchmarks/step18_execution_scoped_events.py` as a
non-blocking step (mirroring Step 5's exact `tee` + `upload-artifact`
pattern, across all three matrix Python versions), uploading its
output as a CI artifact. This validates that **the benchmark executes
successfully** on every supported Python version — it is explicitly
not converted into a performance gate: no threshold assertion exists
anywhere in the script, and CI failure here means only "the benchmark
script itself failed to run," never "a performance number was too
high." Local YAML syntax validated (`yaml.safe_load`) prior to the
real run below.

### 18H-14/18H-15: evaluation and diff review

This section is that evaluation update. Diff review: `git status
--short` shows `benchmarks/step18_execution_scoped_events.py` (new),
`.github/workflows/ci.yml` (modified, +8 lines mirroring the existing
Step 5 pattern), and this evaluation update — no other files touched
by 18H. Full local gate re-run after all 18H changes: `ruff format
--check .` clean, `ruff check .` clean, `pytest -q` 461 passed
(unchanged — the benchmark and CI workflow are outside the test
suite's scope by design).

### 18J (pulled forward): actual CI execution evidence

Branch `feat/step18-event-scoped-delivery-audit` committed
(`6556541`), pushed to `origin`, and opened as PR #25 against `main`
(`https://github.com/payamfirouzfar/RAG-MODULE/pull/25`), which
triggered a real `pull_request`-scoped run of
`.github/workflows/ci.yml` — run ID `32035631246`. This is genuine CI
execution, not a local approximation and not merely YAML-syntax
validation:

```
✓ test (3.10)  — 26s — every step green, including "Step 18 performance
                       benchmark" and "Upload Step 18 benchmark artifact"
✓ test (3.11)  — 20s — same
✓ test (3.12)  — 24s — same
```

Every configured step passed on all three matrix Python versions:
formatting, lint, `mypy`, unit+integration tests, evaluation smoke
test, Step 5 benchmark, **Step 18 benchmark (new)**, package build.
Only non-substantive annotations (GitHub Actions' own Node.js 20
deprecation notice on `actions/checkout@v4` etc., unrelated to this
repository's code) appear in the run's warnings.

**Real CI benchmark artifact** (`step18-execution-scoped-events-benchmark-py3.12`,
downloaded via `gh run download`, not re-run locally and re-typed):

```
python=3.12.13
samples=50000

          tier    p50 (us)    p95 (us)
      no_scope       4.318       4.408
   empty_scope       5.019       5.110
  active_scope       5.009       5.099

scope_check_overhead_p50_pct=16.23%   (tier 2 vs. tier 1)
listener_delivery_overhead_p50_pct=-0.20%   (tier 3 vs. tier 2)
total_scoped_overhead_p50_pct=16.00%   (tier 3 vs. tier 1)
```

**This corroborates, and sharpens, the local 18H-C1 finding.** On the
CI runner (Ubuntu, GitHub-hosted), p50/p95 are nearly identical within
each tier — a far tighter measurement than any local Windows run
produced — and `no_scope` (4.318 µs) sits clearly and consistently
below both scoped tiers (~5.0 µs), with a stable +16% scope-check
delta. The listener-delivery delta (tier 3 vs. tier 2) is effectively
zero (−0.20%), consistent with the local finding that this benchmark's
resolution cannot separate listener-invocation cost from the cost of
merely carrying a non-`None` event_scope. **No new claim is made
beyond what CI evidence supports**: scope-carrying has a real, small,
consistently-measurable cost on this CI environment; listener delivery
itself remains unresolved from tier 2.

**Status upgrade, evidence-based**: 18H's benchmark row moves from
*Benchmark-proven (local); CI pending* to **Benchmark-proven,
CI-proven** — the actual GitHub Actions run, not a local approximation,
is now the evidence of record for "the benchmark executes successfully
on every supported Python version."

## 18I — Final Evaluation

18I implements nothing. Its job is to answer one question: **does the
actual repository state satisfy the frozen Step 18 contract (ADR-022),
with every claim traced to specific evidence** — and to say plainly
where that trace breaks down, rather than filling a gap with prose.

### 18I-1: ADR-022 re-read against current repository state

ADR-022's Status field reads **Proposed** as of this writing
(`docs/architecture/decisions/ADR-022-execution-scoped-event-delivery.md`,
line 5) — unchanged since 18C. This is correct and intentional: ADR
status moves to Accepted only in 18K, after documentation/
compatibility/security/dependency review is complete, matching this
project's established precedent (ADR-018 through ADR-021 all stayed
Proposed through their implementation/test/CI phases). 18I does not
change this.

### 18I-2: requirements matrix re-read against current repository state

`docs/architecture/requirements-matrix-v0.1.md` rows A5 and A10 are
**unmodified** — still reading their original Step-4-era text ("EventBus
must eventually become execution-scoped for isolation" / "process-wide
EventBus remains as compatibility delivery mechanism"), with no
evidence column update yet. This is correct: updating those rows is a
documentation action reserved for 18K, not 18I. 18I's job is only to
confirm the *evidence* now exists to justify that future update, not
to perform it early.

### 18I-3 through 18I-9: reconciliation against the Evidence Matrix

Every row in the Step 18 Evidence Matrix (18A–18J) above was re-read
against this section's own claims before writing this synthesis — no
new claim is introduced here that isn't already backed by a matrix row
citing a specific test name, file, or CI run ID. Specifically
reconciled:

- **Implementation** (18E row): `EventScope`, `ExecutionContext.event_scope`,
  `child()` propagation, `Module.__call__` dual delivery — all four
  ADR-022 Decision-section commitments have a corresponding CI-proven
  matrix row. No implementation commitment in ADR-022's Decision
  section is missing a corresponding row.
- **Unit tests** (18D/18E): 22 EVT-* tests, CI-proven.
- **Integration tests** (18F): 9 tests across `Sequential`, nested
  `Sequential`, `Block`, `RAGModule`, `ExecutionEngine`, CI-proven.
- **Failure tests** (18G): `EVT-FAILURE-001`/`EVT-FAILURE-002`,
  CI-proven.
- **Concurrency evidence** (18G): `EVT-ISOLATION-001` CI-proven;
  `EventBus` thread safety explicitly **not** claimed anywhere, matrix
  row states this directly rather than omitting it.
- **Benchmark** (18H): CI-proven execution; the *interpretation* is
  bounded exactly as strongly as the data supports (scope-carrying
  cost is real and directionally consistent; listener-delivery-only
  cost is not resolved) — no stronger claim appears in this document
  than in the 18H section itself.
- **CI** (18J, pulled forward into 18H): PR #25, run `32035631246`
  (first push) and `32035918122` (confirmed current as of this 18I
  pass — re-checked via `gh pr view 25`, `mergeStateStatus: CLEAN`,
  all three checks `SUCCESS` on the latest commit, not a stale run).

### 18I-10: benchmark interpretation reconciled

No new benchmark claim is made in 18I. The 18H section's own bounded
conclusion stands: `no_scope` measurably and consistently reads below
both scoped tiers on the real CI runner (4.318 µs vs. ~5.0 µs,
Python 3.12.13); the listener-delivery-specific cost (tier 3 vs. tier
2) remains unresolved by this benchmark's methodology. This is
reported as the final Step 18 benchmark evidence, not superseded or
strengthened here.

### 18I-11: deferred risks re-reviewed

`EVT-RACE-001` (global `EventBus` thread safety) and `EVT-FAIL-001`
(listener-failure isolation) remain **Deferred**, both formally
recorded with owner/current-behavior/revisit-trigger fields in the
Deferred Risks table above and in ADR-022 itself. Neither risk is
resolved, newly discovered, or reclassified by 18I — they are
reconfirmed as accurately representing current repository behavior
(verified by re-reading `events.py`: still no lock, no synchronization
primitive, as of this pass).

### 18I-12 through 18I-14: compatibility / security / dependency — scope note

Full compatibility, security, and dependency review is **18K's job**,
not 18I's — conflating them here would violate this project's own
gate separation (evaluation is "did we prove it," not "is it safe to
ship"). ADR-022 already contains preliminary Security and Dependency
Review sections (Q12, and the dedicated Security/Dependency review
sections); 18I confirms these preliminary sections exist and are
internally consistent with the implementation as built (zero new
runtime dependencies confirmed by 18E's diff: only `events.py`,
`context.py`, `module.py`, and two `__init__.py` export lists changed,
no new imports beyond the `TYPE_CHECKING`-guarded `EventScope`
forward reference) — but does not perform the expanded 18K review
itself.

### 18I-15: documentation review — scope note

Same boundary: ADR-022 exists and is internally complete (all 12
decision-gate questions answered, Concurrency/Deferred Risks/CI
strategy sections present); moving its Status to Accepted and updating
the requirements matrix's evidence columns are 18K actions, not
performed here.

### 18I-16: evidence provenance — explicit trace for every headline claim

| Claim | Provenance |
|---|---|
| `EventScope` isolates unrelated executions | SOURCE (independent listener ownership) + TEST (`EVT-ISOLATION-001`) + CI |
| `EventBus` is thread-safe | **NOT ESTABLISHED** — explicitly, in the matrix, in ADR-022, and here |
| 461 tests pass | CI-PROVEN (PR #25, all 3 Python versions) |
| Scope-carrying has measurable overhead | BENCHMARK RESULT, CI-PROVEN, bounded interpretation only |
| Listener-delivery-specific overhead is small | **NOT ESTABLISHED** — benchmark lacks resolution for this specific sub-claim |
| No production architecture change was required | VERIFIED (`git diff --stat` shows zero changes to `sequential.py`/`block.py`/`engine.py`) |
| Step 18 is production-ready | **INVALID** — 18K and 18L have not run |
| ADR-022 is Accepted | **INVALID** — Status field still reads Proposed |

### 18I-17: unsupported claims identified

None found in this document or in ADR-022 that lack a matrix row or
explicit "not established" marker. This is itself worth stating
plainly rather than assuming: the search was performed (re-reading
every status cell in the Evidence Matrix above and cross-checking each
against a named test, file, or CI run) and came back clean — not
skipped.

### 18I-18: evaluation ledger status

This document (`evaluation/step18-evaluation.md`) is itself the
updated ledger — no separate file created, consistent with the
decision made before 18H.

### 18I-19: local gates re-run for this pass

Docs-only change (this section); no source touched. `ruff format
--check evaluation/step18-evaluation.md` run and clean before
committing.

### 18I-20: CI evidence requirements for remaining steps

18K's documentation changes (ADR-022 status, requirements matrix rows)
and 18L's final diff/release gate will each need their own CI
confirmation if they touch any file CI lints/type-checks/tests —
requirements-matrix and ADR markdown changes do not require a new CI
run to be truthful (they're prose, not executable claims), but any
further source/test change would.

## Step 18 completion state (updated through 18H + real CI evidence)

**Step 18 is NOT complete**, but its evidence base is now
substantially stronger. 18A through 18H, plus the core of 18J, have
reached **CI-proven** status via PR #25's real GitHub Actions run
(`32035631246`) — not local approximation, not YAML-syntax validation
only. `test (3.10)`/`test (3.11)`/`test (3.12)` all passed with every
configured step green, including the newly-added Step 18 benchmark
step and its artifact upload.

**18I is now complete** (see the 18I — Final Evaluation section above:
18I-1 through 18I-20, with an explicit evidence-provenance table and a
confirmed-clean unsupported-claims check).

Remaining before Step 18 can be marked Complete:

- **18K** — documentation (ADR-022 → Accepted, requirements matrix
  A5/A10 evidence columns), full compatibility/security/dependency
  review (expanding past the preliminary ADR-022 sections 18I-12
  through 18I-15 confirmed exist but did not expand).
- **18L** — final diff/status/release gate, including the decision of
  whether/when PR #25 merges to `main` and whether a post-merge CI run
  (on `main` itself, not just the `pull_request` trigger) is also
  required before final acceptance — consistent with this project's
  established precedent of treating pre-merge and post-merge CI as
  distinct evidence.

## Conclusion (18A)

Step 18 is **execution-scoped event delivery**, closing the gap named
by requirements A5 and A10 and architecture doc §5's "sibling
isolation" invariant — selected from repository evidence (a stale but
still-accurate "Next priority" item, two open requirement rows, and a
direct code-level confirmation that the gap is real), not intuition.
18B through 18G have since produced ADR-022 (Proposed), a frozen and
implemented contract, integration proof across every real composition
path, and formally-recorded concurrency/failure-isolation evidence
(including two deferred risks, EVT-RACE-001 and EVT-FAIL-001, tracked
rather than silently absorbed). The next action is **18H: benchmark**,
following ADR-022's three-tier methodology, not before this evidence
matrix existed as a durable artifact — see Status above.
