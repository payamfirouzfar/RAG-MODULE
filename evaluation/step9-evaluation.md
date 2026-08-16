# Step 9 Evaluation — Architecture Snapshot Validation

Date: 2026-08-16

Branch: `feat/step9-architecture-validation`, based on `main` after
PR #3 (Steps 7+8) was merged with explicit approval.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-013, this
evaluation proves: is an `ArchitectureSnapshot` a well-formed,
non-empty rooted tree — checked independently of execution, with no
provider/LLM/database/network involvement.

## Contract

`validate_snapshot(snapshot: ArchitectureSnapshot) -> None`, raising
`ValidationError` (reused, no new exception type) on the first
violation of the ten-rule non-empty-rooted-tree contract (ADR-013),
checked in a fixed order: empty → duplicate IDs → dangling references
→ self-containment → multiple parents → root count → reachability.

## Deterministic evaluation matrix

| Case              | Expected | Result |
| ----------------- | -------- | ------ |
| Empty              | invalid    | PASS |
| Single node        | valid       | PASS |
| Two-node tree       | valid        | PASS |
| Deep tree (4 levels) | valid        | PASS |
| Branching tree        | valid        | PASS |
| Duplicate ID          | invalid      | PASS |
| Dangling child (missing parent) | invalid  | PASS |
| Dangling child (missing child)     | invalid  | PASS |
| Self-child                             | invalid  | PASS |
| Multiple parents (diamond)                 | invalid  | PASS |
| Zero roots (connected cycle)                   | invalid  | PASS |
| Multiple roots                                    | invalid  | PASS |
| Disconnected node                                     | invalid  | PASS |
| Disconnected cycle                                        | invalid  | PASS |

```
case_count: 14
error_count: 0
expected_outcome_accuracy: 1.0
```

## Functional results

22 new tests (19 unit in `tests/unit/core/test_architecture.py` + 3
integration in `tests/integration/test_architecture_validation.py`).
Combined with the pre-existing 202, total suite is 224.

| Invariant                                                                       | Result |
| -------------------------------------------------------------------------------------- | ------ |
| One/two/deep/branching-node trees all validate successfully (`None`, no raise)            | PASS |
| Empty snapshot rejected                                                                       | PASS |
| Duplicate node ID rejected, with the specific id named in the error                               | PASS |
| Dangling parent/child references rejected independently (two separate tests)                          | PASS |
| Self-containment (`parent_id == child_id`) rejected                                                        | PASS |
| **Diamond** (`A→B`, `A→C`, `B→D`, `C→D`) rejected — proves "exactly one root" alone is insufficient (Staff correction #2), verified by direct construction before being written into ADR-013, now covered by a dedicated test | PASS |
| Connected cycle (`A→B→C→A`) rejected via zero-roots check                                                        | PASS |
| Multiple roots rejected                                                                                              | PASS |
| Disconnected node (isolated, zero edges) rejected — caught as a second root                                            | PASS |
| **Disconnected cycle** (`A→B` valid + `C→D→C` cycle) rejected via reachability, not root-count — proves reachability catches what root-counting alone misses | PASS |
| Validation does not mutate `nodes`/`children`                                                                                | PASS |
| Validation is deterministic on both success and failure (same error message twice)                                              | PASS |
| Real `Module` tree → `snapshot()` → `validate_snapshot()` succeeds with no provider/LLM/database/network                            | PASS |
| A validated snapshot still supports `inspect()` unchanged                                                                                | PASS |
| No `get_type_hints`/`eval`/`exec`/`vars(` in `architecture.py` (source inspection)                                                            | PASS |
| No provider import in `architecture.py` (AST-based check, reusing the Step 7/8 pattern)                                                            | PASS |

## Test results

```
pytest:  224 passed (202 pre-existing, unmodified + 22 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 22 source files
coverage:      99% overall; architecture.py 98% (one line)
```

Also verified directly against Python 3.10 (`py -3.10`), per the
Step 7 lesson: 224/224 passed, mypy clean.

### The one uncovered line in `architecture.py`

The reachability walk's "already visited, skip" guard
(`if current in reachable: continue`) is structurally unreachable
under the invariants already enforced earlier in the same function:
by the time the reachability walk runs, Rule 5 (at most one parent per
node) has already passed, which means no node can be pushed onto the
traversal stack more than once via `children_by_parent`. This was
verified directly (not assumed) before deciding to keep the line as
defensive code rather than remove it purely to reach 100% coverage —
removing it would make the BFS/DFS pattern fragile to a future change
that altered the ordering of checks.

## Performance

`benchmarks/step9_architecture_validation.py`, Windows, Python 3.12.0,
local. Trees built via the real `Module` → `snapshot()` path, not
hand-constructed dataclasses, for the scaling measurements.

| Operation                                              | p50 (µs) |
| ------------------------------------------------------------ | -------- |
| `validate_snapshot()` — 1 node                                   | 1.0      |
| `validate_snapshot()` — 10 nodes                                     | 3.8      |
| `validate_snapshot()` — 100 nodes                                        | 31.6     |
| `validate_snapshot()` — 1,000 nodes                                          | 330.2    |
| `validate_snapshot()` — duplicate id (fails at the earliest check)               | 0.7      |
| `validate_snapshot()` — disconnected cycle, 100 nodes (fails after reachability)     | 35.4     |

### Empirical O(N+E) confirmation

| N growth | p50 growth | Linear would predict | Quadratic would predict |
| -------- | ---------- | --------------------- | ------------------------- |
| 1 → 10   | 3.8x       | 10x                       | 100x |
| 10 → 100 | 8.3x       | 10x                          | 100x |
| 100 → 1000 | 10.4x    | 10x                             | 100x |

Growth stays close to linear (10x node count → roughly 8-10x time), not
quadratic — confirming the design's O(N+E) claim empirically, not just
by inspection of the algorithm. (The 1→10 step measures below 10x
likely because fixed per-call overhead, e.g. dict/set allocation, is
proportionally larger relative to the tiny 1-node case.)

The duplicate-id failure (0.7µs) is far cheaper than any valid-tree
walk, confirming the fixed check order fails fast on the cheapest
check first. The disconnected-cycle failure (35.4µs, close to the
31.6µs cost of a fully valid 100-node tree) confirms it pays nearly
the full cost, since reachability is the last and most expensive check
in the sequence — exactly the expected shape given ADR-013's fixed
algorithm order.

## Compatibility review

| Existing API        | Step 9 effect |
| -------------------- | -------------- |
| `Component`          | none — zero lines touched |
| `Module.__call__`    | none — zero lines touched |
| `Sequential`         | none — zero lines touched |
| `ExecutionEngine`    | none — zero lines touched |
| `ExecutionContext`   | none — zero lines touched |
| `ports.py`           | none — zero lines touched |
| `inspection.py`      | none — zero lines touched (validated, never modified) |
| existing exceptions  | unchanged — `ValidationError` reused, no new type |
| public snapshot API  | preserved — `snapshot()`/`Module.snapshot()`/`inspect()` all unchanged |

All 202 pre-existing tests pass **unmodified**.

## Security review

| Question                                    | Answer |
| ------------------------------------------------ | ------ |
| Does validation inspect arbitrary component objects? | No — only `ArchitectureNode.id`/`ArchitectureChild.parent_id`/`child_id` are read |
| Does it execute component code?                          | No |
| Does it evaluate annotations?                                | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Does it deserialize untrusted data?                              | No — no serialization format exists yet (ADR-012 Non-goals) |
| Does it mutate architecture?                                        | No — proven by dedicated test, not merely asserted |

## Dependency review

Zero new runtime dependencies. `architecture.py` imports only
`ragtorch.core.errors` and `ragtorch.core.inspection` (existing
internal modules). Confirmed via AST-based import inspection test.

## Diff review

Scope: `src/ragtorch/core/architecture.py` (new), `core/__init__.py` +
top-level `__init__.py` (export, 100%-parity convention),
`test_architecture.py` (new), `test_architecture_validation.py` (new),
`test_public_api.py` (1 entry), `benchmarks/step9_architecture_validation.py`
(new), ADR-013 (new, amended pre-implementation, to be accepted
post-CI), requirements matrix (A29+, pending). No touch to
`Component`, `Module`, `ExecutionEngine`, `ExecutionContext`,
`Sequential`, `ports.py`, or `inspection.py`.

## Limitations (explicitly named, not silently absorbed)

- **The pre-existing `Module` cycle-registration gap remains
  unaddressed.** `a.child = b; b.child = a` succeeds silently, and
  `named_modules()`/`snapshot()` subsequently `RecursionError`s rather
  than failing cleanly — verified by direct reproduction. This is
  upstream of `validate_snapshot()`'s scope: a validator operating on
  an already-built `ArchitectureSnapshot` cannot protect against a
  tree that couldn't be constructed in the first place. Named here as
  a real, documented limitation rather than fixed as an out-of-scope
  "emergency patch," per ADR-013's explicit Non-goals.
- **No data-flow validation.** `ArchitectureChild` means containment
  only; `validate_snapshot()` says nothing about whether a retriever's
  output type is compatible with a reranker's input port (that's
  `ports.is_compatible()`'s job, not wired into this validator).

## Decision

**Step 9 Definition of Done: met locally** (Python 3.10 and 3.12 both
verified). Per the project's standing discipline, ADR-013's status
change from Proposed to Accepted is deferred until real GitHub Actions
CI confirmation — not claimed from local checks alone.
