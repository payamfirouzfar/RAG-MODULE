# Step 19 Evaluation — Module Registration Cycle Detection

Date: 2026-08-17 (19A-19H, local) — updated through CI/merge

## Status

**Overall status: IN PROGRESS.**

Step 19 is not complete until 19A-19Q (repository audit through
post-merge closure) have each independently satisfied their required
evidence — matching Step 18's own 17-gate discipline. This document is
the Step 19 evidence ledger, structured identically to
`evaluation/step18-evaluation.md`. No claim here says "Step 19 is
production-ready" until post-merge CI is confirmed.

## Evidence vocabulary

Same frozen vocabulary as Step 18 (Planned / Audited / Designed /
Contract-frozen / Implemented / Test-proven / Benchmark-proven /
Locally verified / CI-proven / Deferred / Blocked / Accepted /
Complete) — not redefined here, reused verbatim for consistency across
the project's evidence ledgers.

## Step 19 Evidence Matrix

| Gate | Area | Requirement / Question | Contract source | Evidence | Local | CI | Status |
|---|---|---|---|---|---|---|---|
| 19A | Audit | Next highest-value gap identified from repository evidence, not intuition | requirements-matrix "Next priority" #4, A29 | candidate table (5 candidates), direct source checks (no `*Provider*` file exists, no cycle-detection code exists, no incremental-validation code exists) | ✓ | N/A | Audited |
| 19B | Selection | Candidate ranked and selected with explicit reasoning | this document / prior conversation turn | Module registration cycle detection selected over incremental-graph-validation (no workload evidence) and provider routing (no provider exists yet) | ✓ | N/A | Designed |
| 19C | Changeability review | Replacement/extension/testability/async/serialization/observation/failure/isolation/API-stability/documentation all considered | prior conversation turn | private `_would_create_cycle` helper (not baked into `register_module`), iterative not recursive, identity-based visited set, no new public API, no new exception type | ✓ | N/A | Designed |
| 19D | ADR decision | Does this require a new architectural decision? | Phase 19H default | **No.** Implementation required no new type, no new public API, no new exception, no lifecycle/concurrency change — purely a private helper enforcing an already-implied invariant ("the module hierarchy is a tree," A29). No ADR-023 created. | ✓ | N/A | N/A — explicitly not required, reasoned not assumed |
| 19E | Public contract | A `Module` cannot be registered as a descendant of itself, directly or indirectly; `RegistryError` (existing type, no new exception) | prior conversation turn | `_would_create_cycle(parent, child)` in `module.py`, called from `register_module` only when `existing is None` (preserves same-instance re-registration) | ✓ | pending | Contract-frozen |
| 19F | Implementation | `_would_create_cycle` + `register_module` integration | contract above | `src/ragtorch/core/module.py` — one new private function, 4 new lines in `register_module` | ✓ | pending | Implemented (local) |
| 19G | Unit tests | Direct self-registration, 2-node cycle, multi-level cycle, valid acyclic registration, diamond sharing (not a cycle), same-instance re-registration preserved, different-instance duplicate still raises, non-Module still raises, rejected-cycle-does-not-mutate-graph, attribute-assignment also protected | contract above | `tests/unit/core/test_module.py`, 11 new tests, all passing locally (26/26 in file) | ✓ | pending | Test-proven (local) |
| 19H | Integration tests | Cycle rejection through `Sequential`'s real registration path (not just bare `Module`), rejected cycle leaves the pipeline traversable and executable | contract above | `tests/integration/test_module_cycle_detection.py`, 3 tests, all passing locally | ✓ | pending | Test-proven (local) |
| 19I | Failure safety | Rejected registration does not mutate `_modules`; `named_children()`/`named_modules()`/`snapshot()` remain correct after rejection | 19G/19H tests | `test_rejected_cycle_does_not_mutate_the_graph`, `test_rejected_cycle_leaves_architecture_traversable` (both unit and integration variants) | ✓ | pending | Test-proven (local) |
| 19J | Regression | Existing `test_module.py` suite (pre-Step-19) passes unchanged | — | All 15 pre-existing tests in `test_module.py` pass unmodified; full suite 474/474 (461 pre-Step-19 + 13 new: 11 unit + 2 integration) | ✓ | pending | Test-proven (local) |
| 19K | Quality | Lint/format/mypy clean | — | `ruff check .`, `ruff format --check .`, `mypy` (bare, CI-scoped) all clean | ✓ | pending | Locally verified |
| 19L | Benchmark | Registration-time cost of cycle detection as subtree size grows | Phase 19G philosophy — measure, don't threshold | `benchmarks/step19_module_cycle_detection.py`: 1/10/100/1,000-node linear chains, ~3.9µs → ~12µs → ~102µs → ~959µs — roughly linear in subtree size, no surprise, no threshold asserted | ✓ | pending (file-only, matching the 12-of-13 majority precedent Step 18's own 18H-1/18H-2 audit established) | Benchmark-proven (local) |
| 19M | Evaluation | This document | this document | Evidence matrix above, provenance traced to specific test names/files | ✓ | N/A | In progress |
| 19N | CI | Actual GitHub Actions execution, not local approximation | `.github/workflows/ci.yml` (unmodified — no new CI step needed; existing "Unit and integration tests" step covers 19G/19H automatically) | pending push/PR | — | pending | Planned |
| 19O | Documentation | Requirements matrix row (A71, deferred until post-merge CI per Step 18's own precedent) | requirements-matrix-v0.1.md | **Deliberately deferred** — same precedent discovered during Step 18's 18K-1 audit (every filled A-row cites post-merge CI) applies here | — | — | Blocked on merge, by design |
| 19P | Compatibility | `Module`/`RegistryError` API unchanged; existing valid trees unchanged; duplicate-registration behavior unchanged; execution/snapshot/inspection unchanged | see Compatibility review below | reviewed against actual diff | ✓ | pending | Locally verified |
| 19Q | Security | Cycle rejection prevents unbounded traversal/recursion; no new externally observable data | see Security review below | reviewed against actual diff | ✓ | N/A | Locally verified |
| 19R | Dependencies | No new dependencies | `pyproject.toml` diff | `git diff` against every manifest file — empty | ✓ | N/A | Locally verified |
| 19S | Diff review | Only intended files changed | `git diff --stat` | see Diff review below | ✓ | N/A | Locally verified |
| 19T | Closure | Merge + post-merge CI | — | pending | — | pending | Planned |

## Public contract (frozen)

```text
A Module may not be registered beneath itself, directly or indirectly.

module.register_module("self", module)                    -> RegistryError
parent.register_module("x", child); child.register_module("y", parent)  -> RegistryError (2-node cycle)
a -> b -> c -> a (any depth)                                -> RegistryError

parent.register_module("child", child)                      -> succeeds (tree)
shared registered under two different parents                -> succeeds (sharing, not a cycle)
same instance re-registered under the same name               -> succeeds (pre-existing behavior, unchanged)
different instance under an existing name                      -> RegistryError (pre-existing "already exists" behavior, unchanged)
non-Module value                                                 -> RegistryError (pre-existing behavior, unchanged)

Failure safety: a rejected registration never mutates _modules.
No new public API, no new exception type. __setattr__-based
registration (self.child = child) is protected automatically,
since it already routes through register_module.
```

## Design rationale (19C, Changeability Review)

- **Replacement**: cycle detection lives entirely behind
  `_would_create_cycle`, a private module-level function — a future
  optimization (e.g. a maintained ancestry index instead of a
  per-registration subtree walk) can replace its internals without
  touching `register_module`'s public behavior or any caller.
- **Extension**: nothing about this design forecloses a future
  `Module.validate()` convenience method, richer diagnostics, or
  graph-serialization validation reusing the same traversal primitive
  — deliberately not built now (Phase 19D/19H: no ADR, no scope
  creep), matching A29's own explicit deferral criterion.
- **Testability**: pure Python object graph, zero external
  dependencies, zero provider/network/service requirement — every
  test uses plain `Module` subclasses.
- **Async**: no `threading`/`asyncio`/`contextvars` introduced;
  `_would_create_cycle` is a plain synchronous function operating on
  the in-memory object graph, no different from every other traversal
  method (`modules()`, `named_modules()`) already in this file.
- **Serialization**: not applicable — no new persistent state, no new
  runtime-only object requiring separation from configuration.
- **Observation**: no new observability surface; cycle rejection
  raises the same `RegistryError` every other invalid-registration
  path already raises, observable identically.
- **Failure**: covered explicitly by 19I — rejected registration is
  atomic from the caller's perspective (`_modules` unchanged), proven
  by direct test, not assumed.
- **Isolation**: not applicable in the concurrency sense — this is a
  single-object-graph invariant, not an execution-scoping concern (no
  relation to ADR-022/Step 18's `EventScope` work).
- **API stability**: zero new public names. `_would_create_cycle` is
  private (leading underscore, not exported from `__init__.py`,
  verified by not adding it to either `__all__` list).
- **Documentation**: this ledger plus inline docstrings on
  `_would_create_cycle` explain the invariant and the identity-vs-
  equality design choice, so a future maintainer doesn't need to
  reverse-engineer why `id()` was chosen over `==`.

## Compatibility review

- **API**: `Module.register_module`'s signature is unchanged
  (`name: str, module: Module) -> None`); `RegistryError` is reused,
  not subclassed or redefined; no new public export anywhere.
- **Behavioral**: existing duplicate-registration behavior (same
  instance under the same name = OK; different instance under an
  existing name = `RegistryError`) preserved exactly — verified by two
  dedicated regression tests
  (`test_same_instance_same_name_reregistration_still_ok_with_cycle_check_present`,
  `test_different_instance_same_name_still_raises_duplicate_error`),
  and by the full pre-existing `test_module.py` suite passing
  unmodified. Non-`Module` registration behavior unchanged
  (`test_non_module_registration_still_raises`). Diamond-shaped
  sharing (the same child registered under two different parents,
  which was always valid and is common in legitimate graphs) is
  explicitly confirmed to remain valid, not a false-positive cycle
  (`test_diamond_shaped_sharing_is_not_a_cycle`).
- **Execution**: `Module.__call__`, event publishing, `Sequential`,
  `Block`, `RAGModule`, `ExecutionEngine` — all untouched; confirmed by
  `git diff --stat` showing only `module.py` changed in `src/`.
- **Snapshot/inspection**: `snapshot()`/`inspect()` call only
  pre-existing traversal methods (`named_children()`,
  `named_modules()`), neither of which is touched by this diff;
  confirmed by `test_rejected_cycle_leaves_architecture_traversable`
  asserting `snapshot()` still returns the correct node count after a
  rejected registration attempt.

## Security review

- Cycle rejection is a direct, intentional mitigation against
  unbounded recursion/traversal — the exact failure mode a
  self-referential module graph would otherwise cause in `modules()`,
  `named_modules()`, `snapshot()`, and potentially `Module.__call__`
  if such a graph were ever executed. This closes a real defect class,
  not merely adds a feature.
- No new externally observable data: `RegistryError`'s message
  includes only `type(module).__name__`/`type(self).__name__` (class
  names), identical in kind to the existing duplicate-registration
  error message's use of `type(existing).__name__`/
  `type(module).__name__` — no instance state, no user data, no
  secrets.
- `_would_create_cycle`'s visited set uses `id()` values (memory
  addresses within the process), never exposed in any exception
  message or return value — purely an internal traversal
  optimization, not observable data.

## Dependency review

`git diff` against `pyproject.toml`/`requirements.txt`/`setup.py`/
`setup.cfg` (none of the latter three exist in this repository) — zero
changes. `module.py`'s existing import block is unmodified; no new
import was needed (`_would_create_cycle` uses only built-in `set`,
`list`, and the existing `Module.children()` method).

## Diff review

```
git diff --stat (working tree, pre-commit)
 benchmarks/step19_module_cycle_detection.py       | new
 src/ragtorch/core/module.py                        | +19, -0 (approx)
 tests/integration/test_module_cycle_detection.py  | new
 tests/unit/core/test_module.py                     | +100 (approx)
```

Every changed/new file has a Step 19 reason: no unrelated refactor, no
formatting-only churn outside the touched functions, no accidental
file inclusion. Confirmed via `git status --short` immediately before
staging.

## Benchmark strategy (19L)

Question: does `_would_create_cycle`'s per-registration subtree walk
grow reasonably with subtree size, or is there a surprise (e.g.
accidental quadratic behavior)? Baseline/variant: not a before/after
comparison (there is no "before" — this is new functionality), instead
a shape study across chain lengths 1/10/100/1,000 (worst case: a
linear chain, no branching, so `_would_create_cycle` visits every
node). Result: 3.9µs → 12.1µs → 102µs → 959µs — consistent with linear
(O(n)) growth, no surprise. No threshold asserted; not wired into CI,
matching the majority (12 of 13) file-only benchmark precedent this
project established during Step 18's own 18H-1/18H-2 audit.

## What remains before Step 19 can be marked Complete

- **19N** — push branch, open PR, real CI execution (not local
  approximation) on all three Python versions.
- **19O** — requirements matrix A71 row, deliberately deferred until
  post-merge CI evidence exists (same precedent discovered in Step
  18's 18K-1).
- **19T** — merge, post-merge CI confirmation on the actual merged
  `main` SHA, then final closure record.
