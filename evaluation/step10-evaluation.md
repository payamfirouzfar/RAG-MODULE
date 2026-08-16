# Step 10 Evaluation — Composition Preconditions

Date: 2026-08-16

Branch: `feat/step10-composition-preconditions`, based on `main` after
PR #4 (Step 9) was merged with explicit approval.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-014, this
evaluation proves: given two `Port` objects, does `check_connection()`
correctly enforce (raise/pass) exactly what `is_compatible()` already
decides — with no duplicated compatibility logic, no mutation, and no
integration with `ArchitectureSnapshot`/`validate_snapshot()` (that
remains explicit future work for a `Block`/composition layer).

## Contract

`check_connection(output: OutputPort, input: InputPort) -> None`,
raising `ValidationError` (reused, no new exception type) naming both
port names and both type names when `is_compatible(output, input)` is
`False`; returns `None` when `True`. Body is exactly `if not
is_compatible(...): raise ...` — no parallel `issubclass()` logic.

## Correctness

| Case                                                    | Expected | Result |
| -------------------------------------------------------- | -------- | ------ |
| Exact-type match                                          | `None`     | PASS |
| Compatible subtype                                            | `None`      | PASS |
| Incompatible types                                                 | raises `ValidationError` | PASS |
| Error message contains output port name                                | PASS       | PASS |
| Error message contains input port name                                     | PASS          | PASS |
| Error message contains both type names                                         | PASS             | PASS |
| Repeated invocation is deterministic (same result both times)                      | PASS                | PASS |
| No mutation of either `Port` object                                                    | PASS                    | PASS |
| Works across different valid class types (e.g. `object` input accepting `str`)             | PASS                        | PASS |
| Integration: Retriever→Reranker chain (compatible)                                             | `None`                          | PASS |
| Integration: Retriever→Generator (deliberately incompatible)                                       | raises                              | PASS |

```
case_count: 11
error_count: 0
expected_outcome_accuracy: 1.0
```

Behavior for non-`Port` arguments (e.g. `None`) is intentionally
**not** tested — per ADR-014's Argument contract section, no specific
failure mode is guaranteed for that case, so no test encodes one.

## API quality

| Property                                                                 | Result |
| ------------------------------------------------------------------------- | ------ |
| `is_compatible()`'s existing `bool` contract unchanged (explicit regression test: `True` for valid, `False` for invalid, both asserted after `check_connection()` was added) | PASS |
| `check_connection()` never re-implements `issubclass()` — single source of truth is `is_compatible()` (verified by reading the implementation, not merely asserted) | PASS |
| Clear Ask (`is_compatible`, bool) vs. Enforce (`check_connection`, raises) distinction, matching the codebase's existing raising-precondition convention (`validate_snapshot()`, `Port.__post_init__`) | PASS |
| Public export parity: `check_connection` present in both `ragtorch.core.__all__` and `ragtorch.__all__` | PASS |

## Functional results

14 new tests (11 unit in `tests/unit/core/test_ports.py` + 3
integration in `tests/integration/test_component_ports.py`). Combined
with the pre-existing 224, total suite is 238.

| Invariant                                                                                       | Result |
| -------------------------------------------------------------------------------------------------- | ------ |
| `check_connection()` returns `None` for exact-type and subtype-compatible pairs                        | PASS |
| `check_connection()` raises `ValidationError` for incompatible pairs                                       | PASS |
| Error message names both port names and both type names                                                       | PASS |
| `is_compatible()`'s `bool` return is unchanged after `check_connection()` was added (regression pair)              | PASS |
| Deterministic across repeated calls, both success and failure paths                                                    | PASS |
| No mutation of either `Port` (frozen dataclasses; also explicitly re-asserted post-call)                                   | PASS |
| Works with a different valid pairing (`object` input port accepts any output type)                                            | PASS |
| Retriever→Reranker→Generator chain: compatible segments pass via `check_connection()`                                             | PASS |
| Retriever→Generator (deliberately incompatible) raises via `check_connection()`                                                       | PASS |
| No `get_type_hints`/`eval`/`exec` in `ports.py` (source inspection, now covering `check_connection()` too)                                | PASS |
| No provider import in `ports.py` (AST-based check, reusing the Step 7 pattern)                                                                | PASS |

## Test results

```
pytest:        238 passed (224 pre-existing, unmodified + 14 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 22 source files
coverage:      99% overall; ports.py 100%
```

Also verified directly against Python 3.10 (`py -3.10`): 238/238
passed, mypy clean — per the Step 7 lesson that local green on one
interpreter is not evidence for another.

## Performance

`benchmarks/step10_composition_preconditions.py`, Windows, Python
3.12.0, local.

| Operation                              | p50 (µs) |
| ----------------------------------------- | -------- |
| `is_compatible(valid)`                       | 0.100    |
| `check_connection(valid)`                        | 0.100    |
| `check_connection(invalid, raises)`                  | 0.800    |

`check_connection(valid)` is indistinguishable from
`is_compatible(valid)` at this resolution — matching the prediction
that the only added cost on the success path is one conditional that
evaluates to "don't raise." `check_connection(invalid)` costs ~0.7µs
more than the valid path, consistent with the added f-string
construction and exception raise on the failure path. No hard
threshold asserted, consistent with prior benchmarks' methodology;
numbers are measured and reported as-is.

## Compatibility review

| Existing API          | Step 10 effect |
| ------------------------ | -------------- |
| `Component`               | none — zero lines touched |
| `Module`/`Sequential`          | none — zero lines touched |
| `ExecutionEngine`/`ExecutionContext` | none — zero lines touched |
| `ArchitectureSnapshot`/`inspection.py` | none — zero lines touched |
| `validate_snapshot()`/`architecture.py`    | none — zero lines touched |
| `InputPort`/`OutputPort`/`is_compatible()`     | none — zero lines touched, only a new function added below them in the same file |
| existing exceptions                                | unchanged — `ValidationError` reused, no new type |

All 224 pre-existing tests pass **unmodified**.

## Security review

| Question                                              | Answer |
| ---------------------------------------------------------- | ------ |
| Does `check_connection()` execute component code?               | No |
| Does it evaluate annotations or use reflection?                     | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Does it import any provider/model dependency?                          | No — verified by AST-based import inspection |
| Does it mutate either `Port`?                                             | No — proven by dedicated test, not merely asserted |
| Does it inspect arbitrary component state?                                   | No — reads only `output.type`/`input.type`/`output.name`/`input.name`, all already-validated at `Port` construction (ADR-011) |

## Dependency review

Zero new runtime dependencies. `ports.py` imports only
`ragtorch.core.errors` (existing internal module) plus the standard
library `types`/`dataclasses`, unchanged from Step 7. Confirmed via
the existing AST-based import inspection test.

## Diff review

Scope: `src/ragtorch/core/ports.py` (`check_connection()` added,
below `is_compatible()`), `core/__init__.py` + top-level `__init__.py`
(export, 100%-parity convention), `test_ports.py` (11 new unit tests),
`test_component_ports.py` (3 new integration tests),
`test_public_api.py` (1 entry), `benchmarks/step10_composition_preconditions.py`
(new), ADR-014 (amended pre-implementation with the 4 requested
corrections, to be accepted post-CI), requirements matrix (A37+,
pending). No touch to `Component`, `Module`, `Sequential`,
`ExecutionEngine`, `architecture.py`, or `inspection.py` — confirmed
by `git diff --stat` against `main`.

## Limitations (explicitly named, not silently absorbed)

- **No integration with `ArchitectureSnapshot`/`validate_snapshot()`.**
  `check_connection()` operates purely on two `Port` objects passed
  explicitly by the caller; it is not wired into snapshot validation,
  and `ArchitectureNode.input_ports`/`output_ports` remain
  empty-by-default with no discovery mechanism (unchanged from ADR-012).
  This is by design, not an oversight — see ADR-014's Non-goals.
- **No `Block`/composite type introduced.** This step proves the
  precondition primitive in isolation; a future composition layer is
  expected to consume it, not built here.
- **Argument contract is intentionally unenforced.** Passing a
  non-`Port` object is programmer misuse with unspecified failure
  behavior (likely `AttributeError`, not `ValidationError`) — stated
  explicitly in ADR-014 rather than silently implied.

## Decision

**Step 10 Definition of Done: met locally** (Python 3.10 and 3.12 both
verified). Per the project's standing discipline, ADR-014's status
change from Proposed to Accepted is deferred until real GitHub Actions
CI confirmation — not claimed from local checks alone.
