# Step 3 Evaluation — Execution Engine + Module Lifecycle + Observability Contract

Date: 2026-08-15

## Functional

| Component                          | Result |
| ------------------------------------ | ------ |
| ExecutionEngine.execute() success path  | PASS |
| ExecutionEngine context propagation        | PASS |
| ExecutionEngine failure re-raise               | PASS |
| ObservabilityLevel.OFF (Run only)                 | PASS |
| ObservabilityLevel.BASIC (+ duration metric)         | PASS |
| ObservabilityLevel.DEBUG (+ span, + log events)         | PASS |
| Engine over Sequential (composite) pipeline               | PASS |
| Engine failure inside a composite pipeline                  | PASS |
| Independent execute() calls don't leak state                  | PASS |
| Evaluator composes with engine-driven system                    | PASS |

125/125 tests passing (`pytest`), across `tests/unit/core`,
`tests/unit/evaluation`, `tests/unit/test_public_api.py`, and
`tests/integration/`.

## Regression

All 80 Step 1 + Step 2 core unit tests re-verified passing unchanged
(`test_module`, `test_sequential`, `test_config`, `test_errors`,
`test_events`, `test_context`, `test_run`, `test_trace`, `test_metrics`,
`test_logging`). No public API from Steps 1-2 broke.

One correction made during test-writing, not after: an early draft of the
engine unit tests assumed `Boom()` (a Module raising `ValueError` from
`forward()`) would propagate a raw `ValueError` through the engine. It
doesn't — `Module.__call__` (Step 1, unchanged) wraps `forward()`
exceptions in `ExecutionError`. The engine's job is only to *observe* that
error, not change what's raised, so the tests were corrected to expect
`ExecutionError` with the original `ValueError` as `__cause__`. This is
recorded here because it's exactly the kind of assumption that a quick
"seems to work" pass would have missed — the test suite caught it before
merge, as intended.

## Quality

| Check          | Result |
| -------------- | ------ |
| Lint (ruff)    | PASS, 0 issues |
| Format (ruff format --check) | PASS |
| Type check (mypy --strict) | PASS, 0 errors, 18 source files |
| Package build (editable install) | PASS |

## Performance

`evaluation/step3_benchmark.py`, Windows, Python 3.12. Budgets frozen in
ADR-006.

| Level                          | p50 (µs) | p95 (µs) | p99 (µs) |
| -------------------------------- | -------- | -------- | -------- |
| Raw `Module.__call__` (baseline)     | 1.7      | 3.2      | 5.3      |
| `ExecutionEngine` at OFF                 | 6.2      | 11.1     | 34.3     |
| `ExecutionEngine` at BASIC (default)         | 6.7      | 12.1     | 33.9     |
| `ExecutionEngine` at DEBUG                       | 10.9     | 20.4     | 46.6     |

| Budget (ADR-006)                                     | Measured | Result |
| ------------------------------------------------------ | -------- | ------ |
| BASIC overhead over raw call: < 50 µs p50                 | 5.0 µs   | PASS |
| DEBUG additional overhead over BASIC: < 25 µs p50            | 4.2 µs   | PASS |

Both budgets pass with wide margin (10x and 6x headroom respectively).
Consistent with Step 2's own finding that Run+Trace+Metrics wiring costs
roughly single-digit microseconds — the engine adds negligible coordination
overhead on top of the primitives it composes. Interestingly, `OFF` and
`BASIC` measure within noise of each other (6.2 µs vs 6.7 µs) — `Run`
tracking (not gated by `ObservabilityLevel`, per ADR-006: "Run is still
tracked... not optional") dominates the OFF-level cost, and the single
`MetricsCollector.record()` call BASIC adds on top is cheap enough to be
within measurement noise on this machine.

## API stability

New public surface in `ragtorch.__init__` (core kernel): `ExecutionEngine`,
`ExecutionResult`, `ObservabilityLevel`. Guarded by
`tests/unit/test_public_api.py`.

## Reproducibility

No randomness introduced. `ExecutionEngine.execute()` is deterministic
given a deterministic `Module` and explicit `ExecutionContext`.

## Security

No new persistence surface — `ExecutionEngine` does not write to disk in
this step (deferred per ADR-006's Persistence section). Structured logging
calls (`log_event` at DEBUG level) only pass `module` (a class name) and
`error_type` (an exception class name) as fields — never the raw input,
output, or exception message — consistent with R10 and the redaction rule
established in ADR-003.

## Scope compliance

Confirmed no LLM, embedding, vector-database, LangChain/LangGraph, routing,
or optimization code introduced. `ExecutionEngine` depends only on
`ragtorch.core` primitives already built in Steps 1-2.

## Architecture check

- `Module` (Step 1) is unchanged: still computation-only, still wraps its
  own exceptions in `ExecutionError`.
- `Run` (Step 2) is unchanged: `ExecutionEngine` uses its existing
  `start()`/`succeed()`/`fail()` contract without modification.
- `ExecutionEngine` introduces exactly one new class plus one new enum
  plus one new result dataclass — no competing lifecycle model, no
  duplicate identity scheme (reuses `ExecutionContext.run_id`).
- Public/internal boundary preserved: `ExecutionEngine`/`ExecutionResult`/
  `ObservabilityLevel` are exported; the internal `_maybe_span` helper is
  not.

## Verdict

**Step 3 Definition of Done: met.** `RunArtifact` / local persistence
remains open, explicitly deferred future work per ADR-006 — not part of
this step's scope. Proceed to Step 4 (Composition / Graph) when ready.
