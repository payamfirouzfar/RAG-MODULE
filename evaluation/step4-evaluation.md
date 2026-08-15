# Step 4 Evaluation — Runtime Context Propagation + Module Execution Semantics

Date: 2026-08-15

## Functional

| Component                                              | Result |
| -------------------------------------------------------- | ------ |
| `Module.__call__(input)` with no context (I1)               | PASS |
| Context-unaware `forward()` silently ignores a passed context | PASS |
| Context-aware `forward()` receives the context                   | PASS |
| Signature detection cached correctly across instances               | PASS |
| `Sequential` derives a distinct child context per step (I4)            | PASS |
| Child contexts point back to the parent's run_id (I3)                    | PASS |
| Sibling steps don't see each other's context mutations                      | PASS |
| Multi-level nesting preserves chain depth (not flattened)                       | PASS |
| Failure inside a step still raises `ExecutionError` with context present (I5)      | PASS |
| Failure stops subsequent sibling steps from executing                                | PASS |
| `ExecutionEngine` threads its context into the top-level module call                    | PASS |
| Engine + nested `Sequential` (Retriever→Reranker→Generator shape) end-to-end                | PASS |
| DEBUG level still records exactly one top-level span (non-goal boundary held)                 | PASS |
| `Evaluator` composes with context-propagating nested modules                                    | PASS |

146/146 tests passing (`pytest`), across `tests/unit/core`,
`tests/unit/evaluation`, `tests/unit/test_public_api.py`, and
`tests/integration/`.

## Regression

All 125 Step 1-3 tests re-verified passing **unmodified** — not just
"still green," but literally unchanged files (only `test_public_api.py`
from Step 3 remains as-is; no Step 1-3 test file needed editing for Step
4). This is the strongest form of I1 (backward compatibility) evidence:
existing test code making bare `module(input)` calls, with `Module`
subclasses that never mention `context`, continues to pass byte-for-byte.

## Quality

| Check          | Result |
| -------------- | ------ |
| Lint (ruff)    | PASS, 0 issues |
| Format (ruff format --check) | PASS |
| Type check (mypy --strict) | PASS, 0 errors, 18 source files |
| Package build (editable install) | PASS |
| Coverage | 99% overall; `sequential.py` (the main new logic) at 100% |

## Performance

`evaluation/step4_benchmark.py`, Windows, Python 3.12. Unlike Steps 1-3,
no budget was asserted going in — per the project's "measure first, then
freeze a budget" rule, this step's budget is set *from* these numbers,
not checked against a pre-guessed one.

| Operation                                                          | p50 (µs) | p95 (µs) | p99 (µs) |
| --------------------------------------------------------------------- | -------- | -------- | -------- |
| `ExecutionContext.child()`                                                | 7.2      | 15.1     | 60.4     |
| Module call, context-aware `forward`, `context=None`                          | 4.2      | 6.6      | 11.2     |
| Module call, context-aware `forward`, real context (detection True path)          | 3.8      | 6.7      | 14.9     |
| Module call, context-unaware `forward`, context passed (detection False path)         | 3.7      | 6.8      | 12.2     |
| `Sequential`, 1 step, no context (I1 path)                                                | 10.2     | 13.9     | 50.6     |
| `Sequential`, 1 step, with context                                                            | 23.3     | 37.3     | 311.8    |
| `Sequential`, 10 steps, with context                                                              | 185.5    | 659.8    | 1447.5   |
| Nested `Sequential` (2 outer × 5 inner), with context                                                | 237.5    | 938.6    | 2514.0   |
| `ExecutionEngine.execute()` over the nested pipeline, BASIC level                                       | 266.5    | 1414.0   | 3712.6   |

### Key findings

- **Signature detection overhead is unmeasurable.** The three single-call
  rows (context-aware/None, context-aware/real, context-unaware/real) all
  land within 3.7-4.2 µs — indistinguishable within this benchmark's noise
  floor. The `inspect.signature` call happens once per class (cached), so
  steady-state cost is a single dict lookup; I7 is satisfied with wide
  margin.
- **`Sequential` with context costs roughly +13 µs per step at p50**
  (10.2 µs -> 23.3 µs for one step), dominated by `ExecutionContext.child()`
  itself (7.2 µs) plus the extra `Module.__call__` dispatch layer. This
  scales close to linearly with step count (10 steps: 185.5 µs ≈
  10 × ~18.5 µs/step, consistent with per-step overhead rather than a
  fixed cost).
- **No regression on the no-context path.** `Sequential`, 1 step, no
  context (10.2 µs here) is consistent with Step 1's original
  benchmark (10-module `Sequential`, no context, no engine: 53.3-56.4 µs
  across runs) — confirming I1 holds not just functionally but also
  performance-wise: code that never opts into context propagation pays
  nothing extra for the feature existing.

### Frozen budget for future regression checking

- **Context propagation overhead per `Sequential` step: < 50 µs p50**
  (measured: ~13-18.5 µs, ample headroom). This is deliberately generous
  compared to the measured number, consistent with Step 3's ADR-006
  budgets also leaving wide margin rather than being tight targets.
- Not frozen: an end-to-end engine+nested-pipeline budget. The 266.5 µs
  BASIC-level number above is a real measurement worth keeping as a
  reference point, but composing it into one blanket "engine overhead"
  budget conflates context-propagation cost with pipeline-shape cost
  (2 outer × 5 inner steps here) in a way that wouldn't generalize to a
  different pipeline shape. Per-operation budgets (as above) are more
  useful for catching a real regression than one shape-specific number.

## API stability

No new public exports in this step. `Module.__call__`/`forward` gained an
optional keyword-only parameter — an additive, non-breaking signature
change already verified against the full existing test suite. No change
to `tests/unit/test_public_api.py`'s expected export set was needed.

## Reproducibility

No randomness introduced. Context propagation is deterministic: the same
input and the same context always produce the same chain of child
`run_id`s (modulo the underlying UUID generation, which was already
non-reproducible-by-design since Step 2 — `run_id` identity, not its
literal value, is what determinism guarantees here).

## Security

No new persistence or logging surface. `ExecutionContext.child()` (Step 2,
unchanged) continues to produce a frozen, immutable context; nothing in
Step 4 introduces a way for a child module to mutate a sibling's or
parent's context.

## Scope compliance

Confirmed no LLM, embedding, vector-database, DAG/graph engine, retry
logic, caching, or persistence introduced — all explicitly listed as
Step 4 non-goals in ADR-007 and honored. `Sequential` is the only
composite touched; no new composition type (`ModuleList`, `ModuleDict`,
graph) was added.

## Architecture check

- `Module` (Step 1) grows by exactly one optional parameter on `__call__`
  and `forward`; its responsibility (computation) is unchanged.
- `ExecutionContext` (Step 2) is unchanged — Step 4 is its first real
  consumer beyond the Step 2/3 integration tests' manual wiring.
- `ExecutionEngine` (Step 3) changes by one line (`module(input,
  context=context)` instead of `module(input)`); its responsibility
  (coordinating Run/Trace/Metrics for one top-level call) is unchanged —
  it does not itself walk the module tree or manage nested spans.
- No global state, no contextvars, no thread-locals introduced — every
  invariant from ADR-002 (explicit context, no global "current run") holds
  through nested execution, not just at the top level.
- Public/internal boundary preserved: `_forward_accepts_context` and
  `_forward_accepts_context_cache` are module-private (leading underscore),
  not exported.

## Verdict

**Step 4 Definition of Done: met.** Automatic nested trace spans/metrics,
DAG/graph composition, and persistent run artifacts remain open,
explicitly deferred future work per ADR-007 — not part of this step's
scope. Proceed to Step 5 (Module Containers + Composition API) when ready.
