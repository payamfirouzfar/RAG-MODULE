# Step 15 Evaluation — Plan Execution Runtime Boundary

Date: 2026-08-17

Branch: `feat/step15-plan-execution-runtime-implementation`, based on
`main` after ADR-019's docs-only PR (#16) merged and post-merge CI was
independently confirmed:

- PR #16 (ADR-019 initial contract + 15D adversarial-review
  corrections + requirements matrix A67), merged `3fb8ce9`,
  post-merge CI run `31972814646`, 358/358 on 3.10/3.11/3.12.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-019, this
evaluation proves: given an `ExecutionPlan` and a `StepHandler`, does
`ExecutionEngine.execute_plan` correctly wrap
`Executor.execute(plan, handler)` with the same `Run`/`Trace`/`Metrics`
lifecycle guarantee `execute(module, ...)` already provides for a
single `Module` call — exactly one `Run`, at most one span (named
`"execute_plan"`, `DEBUG` only), one `"execution_plan.duration_s"`
metric — while never injecting `ExecutionContext` into the handler,
never deriving plan order itself, and never modifying `execute(module,
...)`.

## The adversarial review that shaped this implementation

ADR-019 went through a 15A/15B repository audit and a 15D adversarial
review before any code was written, and the review found 7 real
issues, 2 of them BLOCKER-tier:

- **ADV-01 (BLOCKER)**: the ADR's first draft implied a caller could
  "derive per-step context themselves," without stating that the root
  `ExecutionContext` `execute_plan` creates when `context=None` is
  entirely unreachable by the handler. Fixed by adopting an explicit
  policy — `ExecutionContext` propagation into step work is out of
  scope for this API — directly reflected in this implementation's
  **CTX-03** test, which proves `handler` is called with no
  `ExecutionContext` argument at all.
- **ADV-02 (BLOCKER)**: the ADR claimed a future async executor could
  be substituted via `executor`, which ADR-018 already proved is
  structurally impossible. Corrected before implementation began — no
  code was ever written against the false claim.
- **ADV-03/ADV-04 (MAJOR)**: the span name and metric name were left
  as vague placeholders. Frozen to `"execute_plan"` and
  `"execution_plan.duration_s"` respectively — implemented exactly as
  literal strings, verified by **TRACE-03**/**METRIC-01**.
- **ADV-05 (MAJOR)**: the observability-failure policy was
  acknowledged as unresolved but not decided. Frozen to an explicit
  policy (failures are not isolated) and implemented by *not* wrapping
  `metrics.record`/`trace.start_span` in any guard — verified by
  **OBS-01**/**OBS-02**, which assert the actual, frozen behavior
  rather than an aspirational one.
- **ADV-06/ADV-07 (MINOR)**: empty-plan lifecycle completeness and the
  exact success/failure sequence were underspecified. Both are
  directly reflected in **PLAN-01**'s full-lifecycle assertion and the
  implementation's structural mirror of `execute(module, ...)`'s
  existing `try`/`except`/`finally`-free sequence.

All 7 findings are directly reflected in this implementation's test
suite — not generic correctness tests, but regression guards for
specific gaps caught before they could exist in committed code.

## Contract

```python
def execute_plan(
    self,
    plan: ExecutionPlan,
    handler: StepHandler,
    *,
    context: ExecutionContext | None = None,
    executor: Executor | None = None,
) -> ExecutionResult: ...
```

Added to the existing `ExecutionEngine` class in `src/ragtorch/core/engine.py`
— no new module, no new public type. Reuses the engine's existing
`ExecutionResult` (`run`, `trace`, `metrics`, `output` property) and
`_maybe_span` helper exactly as `execute(module, ...)` does, with a new
`_record_plan_duration` helper mirroring `_record_duration`'s existing
shape but using the frozen literal metric name instead of a
module-derived one.

## Correctness

| Invariant | Expected | Result |
| --- | --- | --- |
| Empty plan: full successful lifecycle (status, output, span, metric — not merely "no error") | PASS | PASS |
| Plan iteration delegated entirely to `Executor`, engine never walks `plan.steps` | PASS | PASS |
| Caller-supplied `Executor` is actually used, not silently ignored | PASS | PASS |
| Steps execute in `plan.steps` order via the default `SequentialExecutor` | PASS | PASS |
| Caller-supplied root `ExecutionContext` preserved as `run.context` by identity | PASS | PASS |
| Omitted `context` creates a default `ExecutionContext` | PASS | PASS |
| Handler never receives an `ExecutionContext` argument (ADV-01 regression guard) | PASS | PASS |
| Exactly one span at `DEBUG`, none below | PASS | PASS |
| No per-step spans | PASS | PASS |
| Span name is exactly `"execute_plan"` | PASS | PASS |
| Exactly one metric, named exactly `"execution_plan.duration_s"` | PASS | PASS |
| No metric at `OFF` | PASS | PASS |

```
invariant_count: 12
case_count: 21 (unit) + 3 (integration) = 24
error_count: 0
expected_outcome_accuracy: 1.0
```

## Failure semantics

| Invariant | Result |
| --- | --- |
| The exact original exception object propagates unmodified (`exc_info.value is error`) | PASS |
| Downstream steps never execute after a failure | PASS |
| No `ExecutionResult` is ever returned or accessible after a failure | PASS |
| `Run.fail(exc)`'s contract (independently verified against `Run`'s own public API, since `execute_plan` never returns a `Run` on failure — matching the same "unreachable on failure" shape `execute(module, ...)`'s own existing test suite already has) | PASS |

## Observability-failure behavior (ADR-019 Q15, frozen policy)

| Scenario | Behavior | Result |
| --- | --- | --- |
| `MetricsCollector.record` raises during a successful plan execution | The instrumentation exception propagates from `execute_plan` in place of a successful return — not isolated | PASS (documented, tested via monkeypatch) |
| `Trace.start_span` raises during a successful plan execution | Same — the instrumentation exception propagates in place of a successful return | PASS (documented, tested via monkeypatch) |

This is the exact, deliberate policy frozen in ADR-019 — not a defect
introduced by this implementation. It already existed in `execute(module,
...)` before this ADR, and this implementation does not fix it there
either, consistent with ADR-019's explicit decision not to fix it
unilaterally as an unscoped side effect.

## Functional results

24 new tests: 21 unit in `tests/unit/core/test_engine_plan_execution.py`
(mechanism-level, per the PLAN/CTX/TRACE/METRIC/FAIL/OBS/STATE matrix)
plus 3 integration in `tests/integration/test_engine_plan_boundary.py`
(end-to-end through the public `ragtorch` import surface — a
dependency-aware 3-step RAG-shaped handler chain, a mid-plan failure,
and root-context propagation without handler reachability — renamed
from a would-be `test_engine_plan_execution.py` to
`test_engine_plan_boundary.py` to avoid this repository's established
rootless-layout pytest module-basename collision with the unit test
file, the same class of issue Steps 13 and 14 both hit and resolved
the same way).

Combined with the pre-existing 358 (unmodified), total suite is
358 + 24 = 382, confirmed by direct `pytest` run, not assumed.

| Invariant | Result |
| --- | --- |
| `execute(module, ...)`'s full existing test suite (`test_engine.py`, `test_nested_execution.py`, `test_execution_lifecycle.py`, `test_engine_execution.py`) passes unmodified | PASS |
| `Sequential`'s existing test suite (`test_sequential.py`, `test_sequential_context.py`) passes unmodified | PASS |
| `ExecutionPlan`'s existing test suite (`test_execution_plan.py`) passes unmodified | PASS |
| Same `ExecutionEngine` instance reusable across `execute_plan` and `execute` calls, in any order, without state leaking between calls | PASS |
| No `plan`/`handler`/`executor` state leaks across repeated `execute_plan` calls (behavioral isolation test, not `vars()` inspection — matching ADR-018's own STATE-01/02 precedent) | PASS |

## Test results

```
pytest:        382 passed (358 pre-existing, unmodified + 21 unit + 3 integration)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 26 source files
coverage:      engine.py 100%; overall 99%
```

Also verified directly against Python 3.10 (`py -3.10`): 382/382
passed.

## Performance

`benchmarks/step15_plan_execution_runtime.py`, Windows, Python 3.12.0,
local. Compares `SequentialExecutor().execute(plan, handler)` (baseline)
against `ExecutionEngine(level=...).execute_plan(plan, handler)` at
10/100/1,000 steps for both `BASIC` and `DEBUG`, isolating engine
overhead from ADR-018's already-benchmarked O(n²) context-copying cost
(not re-measured here — that curve was established at up to 100,000
steps in Step 14).

| Steps | Level | Baseline (s) | Engine (s) | Overhead (s) | Baseline µs/step | Engine µs/step |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 10 | basic | 0.000102 | 0.000194 | 0.000092 | 10.21 | 19.41 |
| 10 | debug | 0.000102 | 0.000227 | 0.000125 | 10.21 | 22.72 |
| 100 | basic | 0.000228 | 0.000258 | 0.000030 | 2.28 | 2.58 |
| 100 | debug | 0.000228 | 0.000297 | 0.000069 | 2.28 | 2.97 |
| 1,000 | basic | 0.008511 | 0.008258 | -0.000252 | 8.51 | 8.26 |
| 1,000 | debug | 0.008511 | 0.008922 | 0.000411 | 8.51 | 8.92 |

### Interpretation

This benchmark measures, it does not prove, an overhead bound. At
these small step counts (10-1,000), absolute times are in the tens to
hundreds of microseconds — small enough that a single run's
measurement noise (process scheduling, GC, timer resolution) is
comparable in magnitude to the overhead itself. The 1,000-step/`BASIC`
row shows a *negative* overhead value (-0.000252s) in this run: that is
measurement noise, not evidence the engine is faster than the bare
executor — it should not be read as a real result, and is reported
here as-is rather than smoothed over or excluded. Across the
combinations measured, engine overhead is consistently in the
tens-of-microseconds range per call (roughly the cost of constructing
one `Run`/`Trace`/`MetricsCollector` and, at `DEBUG`, one span plus two
log events), not a per-step cost — it does not visibly grow with plan
size the way ADR-018's context-copying cost does, consistent with the
implementation containing no per-step engine work. A more precise
measurement (more samples, percentile reporting, matching ADR-018's
benchmark methodology) is not attempted here since this benchmark's
purpose is to establish that overhead exists and is roughly
plan-size-independent, not to characterize it precisely — no consumer
of this boundary has yet demonstrated a need for a tighter measurement.

## Compatibility review

| Existing API | Step 15 effect |
| --- | --- |
| `execute(module, ...)` | none — zero lines touched, full existing test suite passes unmodified |
| `Module`/`Sequential` | none — zero lines touched |
| `Run`/`Trace`/`MetricsCollector` | none — zero lines touched; reused as-is |
| `ExecutionContext` (`ragtorch.core.context`) | none — zero lines touched |
| `Executor`/`SequentialExecutor`/`StepHandler`/`StepExecutionContext`/`StepExecutionResult` (`ragtorch.core.execution`) | none — zero lines touched; imported and used, not modified |
| `ExecutionPlan`/`ExecutionStep`/`plan()` | none — zero lines touched |
| existing `ExecutionResult` (engine's own) | none — reused as-is, no field added |
| existing exceptions | unchanged — no new exception type introduced |

All 358 pre-existing tests pass **unmodified**.

## Security review

| Question | Answer |
| --- | --- |
| Does `execute_plan` perform any operation with external effect itself? | No — only calls the caller-supplied `handler` (via `Executor.execute`) and engine-owned `Run`/`Trace`/`Metrics` bookkeeping |
| Does it evaluate annotations, use reflection, `eval`, or `exec`? | No |
| Does it import any provider/model dependency? | No — imports only `ragtorch.core.execution`/`ragtorch.core.execution_plan`, both already-existing internal modules |
| Does it automatically log `StepExecutionContext.results`/`StepExecutionResult.values`/`run.output`? | No — matches `execute(module, ...)`'s existing behavior (it never logs the module's actual input/output either) |
| Does it inject `ExecutionContext` into the handler, creating a new implicit trust/identity channel? | No — explicitly does not, per ADR-019 Q2/ADV-01, verified by CTX-03 |

## Dependency review

Zero new runtime dependencies. `engine.py` gains imports from
`ragtorch.core.execution` (`Executor`, `SequentialExecutor`,
`StepHandler`) and `ragtorch.core.execution_plan` (`ExecutionPlan`) —
both already-existing internal modules, no new package.

## Diff review

Scope: `src/ragtorch/core/engine.py` (modified: new import block, new
`execute_plan` method, new `_record_plan_duration` helper, docstring
update), `tests/unit/core/test_engine_plan_execution.py` (new, 21
tests), `tests/integration/test_engine_plan_boundary.py` (new, 3
tests), `benchmarks/step15_plan_execution_runtime.py` (new). ADR-019
and requirements matrix A67 already merged via PR #16's separate
docs-only review — see that PR's own evidence trail. No touch to
`Component`, `Module`, `Sequential`, `ExecutionContext`,
`CompositionGraph`, `Connection`, `ExecutionPlan`, `execution.py`
(ADR-018) — confirmed by explicit test runs against each of those
files' own test suites, all passing unmodified.

## Known limitations (explicitly named, not silently absorbed)

- **Observability failures are not isolated from execution outcome**
  — a `metrics.record`/`trace.start_span` failure propagates in place
  of the primary result. This is a deliberate, frozen v0.1 policy
  (ADR-019 Q15), not an oversight, and it predates this ADR
  (`execute(module, ...)` has the same gap). Fixing it for both paths
  at once is explicit future work.
- **No per-step spans or metrics.** Explicit Non-goal — see ADR-019
  Q7/Q8/Q13.
- **`ExecutionContext` is not propagated into step work.** A caller
  needing per-step run identity inside their handler must construct
  and thread it themselves, entirely independently of `execute_plan`'s
  own `context` parameter — see ADR-019 Q2/Q6.
- **No async, retries, or timeouts.** `execute_plan` is synchronous
  only, matching `Executor`'s existing constraint.
- **Benchmark precision.** The Step 15 benchmark reports raw
  single-run measurements at small step counts, not percentile
  statistics — sufficient to establish overhead exists and doesn't
  scale with plan size, not to characterize it precisely.

## Decision

**Step 15 implementation Definition of Done: met locally** (Python
3.10 and 3.12 both verified, 382/382, lint/format/mypy clean,
`engine.py` 100% coverage). Requirements matrix A67's evidence is
updated to reflect this implementation only after real CI confirms it
— per the project's standing rule that an ADR decision is not proof
until implementation/tests/CI independently confirm it. **ADR-019's
status remains `Proposed`** — its contract was frozen and
post-merge-CI-confirmed via PR #16, but per Step 13/14's precedent, an
ADR is flipped to `Accepted` only after its *implementation* is
independently post-merge-CI-confirmed on `main`, not merely its
docs-only contract. That flip happens in the completion PR, after this
implementation PR merges and post-merge CI confirms it — not now.

## Completion record

Pending PR creation, PR CI, merge, and post-merge CI on `main` — this
section is completed only after all of those are independently
confirmed, matching Steps 13/14's exact discipline.
