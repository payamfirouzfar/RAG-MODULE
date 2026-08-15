# Step 6.2 Evaluation — Component Structural Contract

Date: 2026-08-16

Branch: `feat/step6-component-contract`, PR #2

## Scope

Step 6.2 is an architectural contract change, not a RAG-quality feature.
Per the project's own rule ("evaluation must measure the feature's
intended behavior, not blindly use the same metric for every feature"),
this evaluation focuses on contract conformance, backward compatibility,
context/error semantics, provider independence, and performance — not
retrieval or generation quality, which don't exist yet.

## Functional

| Invariant                                                          | Result |
| ---------------------------------------------------------------------- | ------ |
| Existing `Module` subclass satisfies `Component`                          | PASS |
| `Module.name` returns existing `_name` identity                              | PASS |
| `Module.component_type` returns `type(self).__name__`                           | PASS |
| Independent, non-`Module` class satisfies `Component`                              | PASS |
| Deliberately incomplete class does NOT satisfy `Component`                            | PASS |
| Component invocation works without context                                               | PASS |
| Component invocation works with explicit context                                            | PASS |
| Generic input/output typing works for a non-str, non-Module implementation                      | PASS |
| Existing `ExecutionError` behavior unchanged on failure                                            | PASS |
| No `Component` conformance check on any hot execution path                                             | PASS (verified by inspection: `Module.__call__`, `ExecutionEngine.execute`, `Sequential.forward` unchanged) |

11 new contract tests (`tests/unit/core/test_component.py`), all passing,
Source: CI (see below).

## Regression

All 148 pre-existing tests pass **unmodified** — no existing test file
required editing. `Module.__call__`, `forward`, registration, event
emission, and error wrapping are byte-for-byte unchanged; only two new
properties (`name`, `component_type`) were added.

## Quality (Source: LOCAL, then CI — see below)

| Check          | Result |
| -------------- | ------ |
| Lint (ruff)    | PASS, 0 issues |
| Format (ruff format --check) | PASS |
| Type check (mypy, project's configured `[tool.mypy]` scope) | PASS, 0 errors, 19 source files |
| Coverage | 99% overall; `component.py` 100% |

## CI verification — Source: CI (GitHub Actions)

PR #2, run [31915309706](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31915309706).
Per the project's standing rule since Step 5 ("local green != project
green" — CI silently never executed for Steps 2-4 due to a YAML bug),
this is not claimed as verified until observed actually running:

| Python | Format | Lint | Type check | Tests | Evaluation smoke | Benchmark | Build | Result |
| ------ | ------ | ---- | ----------- | ----- | ----------------- | --------- | ----- | ------ |
| 3.10   | PASS   | PASS | PASS        | 159 passed | PASS          | PASS      | PASS  | success |
| 3.11   | PASS   | PASS | PASS        | 159 passed | PASS          | PASS      | PASS  | success |
| 3.12   | PASS   | PASS | PASS        | 159 passed | PASS          | PASS      | PASS  | success |

Every step of every job verified individually via the Actions API
(`gh api .../jobs/{id}` step-level `conclusion`), not inferred from the
job's overall status alone.

## Performance

`benchmarks/step6_component_contract.py`, Windows, Python 3.12.0, local
(the CI benchmark step ran the same script but did not archive numeric
output for this PR — see CI requirements for Step 5's more elaborate
artifact-upload pattern, not replicated here since Step 6 introduced no
new hot-path code to justify it).

| Operation                                                          | p50 (µs) | Baseline (Steps 1-5) | Regression? |
| --------------------------------------------------------------------- | -------- | ---------------------- | ------------- |
| `Module(input)`                                                          | 1.9      | ~1.9                     | None |
| `Sequential(10)(input)`                                                     | 20.4-20.5 | ~20.6                     | None |
| `module.name`                                                                 | 0.1      | n/a (new)                   | — |
| `module.component_type`                                                         | 0.1      | n/a (new)                     | — |
| `module.inspect()`                                                                 | 1.2      | ~13.4 (different workload; see note) | — |
| `isinstance(module, Component)` [informational, not hot-path]                        | 0.3      | n/a (new)                     | — |

**Note on `inspect()`:** the 1.2µs figure here is not comparable to the
Step 1 baseline's 13.4µs — that baseline used an 11-module tree; this
benchmark's `Identity()` module has no children. Not a regression, a
different workload; flagged here rather than presented as an
apples-to-apples number.

**Conclusion:** no measurable regression on the two hot paths that
matter (`Module.__call__`, `Sequential`). `isinstance(module, Component)`
has a real, non-trivial cost (0.3µs, ~16% of a bare `Module` call) —
exactly why ADR-010 makes it a hard rule that this check never appears
on a hot execution path, rather than an assumption that a Protocol
"probably doesn't cost anything."

## Evaluation (architecture invariants, not RAG quality)

Using the existing `ragtorch.evaluation` infrastructure (no new
subsystem introduced):

```
case_count: 3
error_count: 0
mean exact_match: 1.0
```

Cases proved: `Module` and an independent `ExternalComponent` both
satisfy `Component` inside the evaluated system; execution behavior is
unchanged under evaluation.

## Documentation

- ADR-010 written before implementation, with a Staff-review correction
  applied to the identity-stability wording before code was written.
- `docs/architecture/v0.1-architecture.md` §3 rewritten to describe
  `Component` as implemented (with a structural diagram) rather than as
  a forward-reference.
- `docs/architecture/requirements-matrix-v0.1.md`: A1 updated with
  implemented evidence; A13-A16 added, including an honest gap note on
  A16 (the hot-path rule is currently enforced by documentation + review,
  not an automated architecture-test guard).

## Compatibility review

- `Module(...)`, `RAGModule(...)`, `Sequential(...)`: unchanged, verified
  by the full existing test suite passing unmodified.
- `forward()`, `__call__()`, context propagation, events, errors,
  inspection, registration: unchanged — confirmed by diffing
  `module.py` directly (exactly two properties added; no other line
  touched inside the class body's existing methods).
- No test was modified to accommodate this change.

## Security review

| Question                              | Answer |
| ---------------------------------------- | ------ |
| Global mutable state introduced?             | No |
| Credentials introduced?                          | No |
| Provider calls introduced?                          | No |
| Secret handling altered?                               | No |
| Arbitrary object serialization introduced?                | No |

## Dependency review

`component.py` imports only `typing` (stdlib) and `ragtorch.core.context`
(under `TYPE_CHECKING`, not a runtime import). `pyproject.toml`
unchanged — confirmed via `git diff pyproject.toml` (empty). Zero new
runtime dependencies.

## Diff review

```
git diff --stat main...feat/step6-component-contract
17 files changed, 1391 insertions(+), 50 deletions(-)
```

Scope matches what was authorized: `component.py` (new),
`module.py` (two properties added), `core/__init__.py` and top-level
`__init__.py` (export), `test_component.py` (new),
`test_public_api.py` (one entry), `benchmarks/step6_component_contract.py`
(new), ADR-009 and ADR-010 (new), requirements matrix and
v0.1-architecture.md (updated). No touch to `engine.py`, `context.py`,
`sequential.py`, or any provider file. (The diff above also includes
carry-forward changes from the Step 5 branch this branch was created
from — `events.py`, `test_events.py`, `ci.yml`, Step 5's own docs —
none of which were modified as part of Step 6.2 itself.)

## Verdict

**Step 6.2 Definition of Done: met.** ADR-010 status updated from
Proposed to Accepted only after real GitHub Actions verification (not
local checks alone) confirmed 159/159 tests passing across all three
supported Python versions. `capabilities`, `configuration`, async,
streaming, serialization, a component registry, and Block/Architecture
composition remain explicitly deferred per ADR-010's Non-goals — not
part of this step's scope. Per the project's stated sequencing, the next
step is Ports/typed I/O contracts (Step 7), not Blocks, Graphs,
providers, routing, async, or streaming.
