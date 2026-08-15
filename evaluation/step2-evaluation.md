# Step 2 Evaluation — Execution, Observability & Evaluation Kernel

Date: 2026-08-15

## Functional

| Component            | Result |
| --------------------- | ------ |
| ExecutionContext        | PASS |
| Run lifecycle             | PASS |
| Trace / Span                | PASS |
| MetricsCollector               | PASS |
| Structured logging (context-aware) | PASS |
| redact() / is_sensitive_key()        | PASS |
| EvaluationCase                          | PASS |
| Metric (ExactMatch, Latency)              | PASS |
| Evaluator                                   | PASS |
| EvaluationResult                              | PASS |
| Full lifecycle integration                      | PASS |

107/107 tests passing (`pytest`), across `tests/unit/core`,
`tests/unit/evaluation`, `tests/unit/test_public_api.py`, and
`tests/integration/`.

## Regression

All 47 Step 1 tests still pass unchanged — no Step 1 public API broke.

## Quality

| Check          | Result |
| -------------- | ------ |
| Lint (ruff)    | PASS, 0 issues |
| Format (ruff format --check) | PASS |
| Type check (mypy --strict) | PASS, 0 errors, 17 source files |
| Package build (editable install) | PASS |

## Performance

`evaluation/step2_benchmark.py`, Windows, Python 3.12.

| Operation                                             | p50 (µs) | p95 (µs) | p99 (µs) |
| ------------------------------------------------------ | -------- | -------- | -------- |
| ExecutionContext creation                                 | 2.9      | 4.9      | 8.0      |
| ExecutionContext.child()                                    | 3.2      | 5.8      | 10.6     |
| Run.start() + succeed()                                       | 3.2      | 6.5      | 27.5     |
| Trace: single span                                              | 2.6      | 6.6      | 18.1     |
| Trace: 10 nested spans                                             | 37.8     | 83.3     | 140.7    |
| MetricsCollector.record()                                            | 0.2      | 0.3      | 0.3      |
| Module call, plain (Step 1 baseline)                                    | 2.8      | 3.9      | 12.2     |
| Module call, wrapped in Run+Trace+Metrics                                  | 11.4     | 22.9     | 57.3     |
| Evaluator.evaluate(), 100 cases, ExactMatch                                   | 134.1 (µs, whole batch) | 235.1 | 444.8 |
| Evaluator.evaluate(), 1000 cases, ExactMatch                                     | 1267.2 (µs, whole batch) | 2029.3 | 2033.3 |

### Observability overhead (R13)

Wrapping a plain Module call with Run + Trace + Metrics costs roughly
**+8.6 µs at p50** (2.8 µs -> 11.4 µs), about 4x the bare call. In absolute
terms this is still far below anything that matters next to real RAG work
(a single embedding call or LLM generation call runs in milliseconds to
seconds), so the current design satisfies "cheap when enabled" — there is
no `observability=False` fast-path yet because there's nothing expensive
enough to need one. This benchmark exists specifically so that claim stays
checked as later steps add heavier tracing (e.g. capturing large
attributes) rather than being assumed.

### Regression found and fixed during this step

The first `Evaluator.evaluate()` benchmark run showed 100-case evaluation
costing ~52 ms — wildly disproportionate to the per-case work (`ExactMatch`
scoring is a single `==` comparison). Root cause:
`EvaluationResult.git_commit` was populated by shelling out to
`git rev-parse --short HEAD` via `subprocess.run` on every call to
`.evaluate()`, once per evaluation *run* rather than per case, but a
subprocess spawn (~50 ms on this machine) still dominated an otherwise
sub-millisecond operation. Fixed by wrapping `current_git_commit()` in
`functools.lru_cache(maxsize=1)`: the commit cannot change within a
process, so caching it is correct, not just fast. Result: 100-case
evaluation dropped from ~52,000 µs to ~134 µs (about 400x), and 1000-case
evaluation now scales roughly linearly with case count as expected
(~1267 µs, i.e. ~1.27 µs/case). This is recorded here rather than silently
fixed, per the "measurable behavior" principle — a benchmark that never ran
would have shipped this as normal.

## API stability

New public surface in `ragtorch.__init__` (core kernel): `ExecutionContext`,
`new_run_id`, `Run`, `RunStatus`, `Trace`, `Span`, `new_span_id`,
`MetricsCollector`, `MetricSummary`, `get_logger`, `log_event`, `redact`,
`is_sensitive_key`.

New public surface in `ragtorch.evaluation` (separate subpackage, not
re-exported from top-level `ragtorch` — see the export-scope decision
recorded in this step's work): `EvaluationCase`, `Metric`, `ExactMatch`,
`Latency`, `Evaluator`, `CaseResult`, `EvaluationResult`,
`current_git_commit`.

Both surfaces are guarded by `tests/unit/test_public_api.py` (core) and
implicitly by the evaluation unit tests (evaluation subpackage).

## Reproducibility

No randomness introduced in Step 2. `EvaluationResult` now also captures
`git_commit` (cached per-process) and `configuration_hash` when supplied,
directly supporting R9 (reproducibility).

## Scope compliance

Confirmed no LLM, embedding, vector-database, LangChain/LangGraph
dependency anywhere in `src/ragtorch`, including the new `evaluation`
subpackage. `Evaluator.evaluate()` accepts any callable system — it has no
dependency on `ragtorch.core.Module`, satisfying ADR-005 (provider
independence) by construction.

## Security

- `redact()` defaults to hiding values (`<redacted Type len=N>`) unless a
  caller explicitly passes `allow=True`.
- `is_sensitive_key()` flags field names containing `key`, `token`,
  `secret`, `password`, or `authorization`.
- No test or benchmark in this step logs a raw payload, prompt, or secret.

## Verdict

**Step 2 Definition of Done: met.** Proceed to Step 3 (Data / Document
abstractions) when ready.
