# Step 12 Evaluation — Composition Graph

Date: 2026-08-16

Branch: `feat/step12-composition-graph`, based on `main` after PR #6
(Step 11) was merged with explicit approval.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-016, this
evaluation proves: given a set of nodes and directed `Connection`s
between them, does `CompositionGraph` correctly enforce all nine
canonical invariants — referential integrity, no duplicate edges,
fan-in ≤ 1 with unrestricted fan-out, acyclicity — as a static,
structural fact, independent of execution.

## Contract

```python
GraphNode(id: str, component: Component)

CompositionGraph(
    nodes: tuple[GraphNode, ...],
    connections: tuple[Connection, ...],
)
```

`CompositionGraph.__post_init__` enforces the nine canonical
invariants from ADR-016, in fixed order, raising `ValidationError`
(reused, no new exception type) on the first violation.
`add_node`/`add_connection`/`remove_node`/`remove_connection` each
return a new, independently-validated `CompositionGraph`.

## Correctness — invariant matrix

| # | Invariant                                              | Expected | Result |
| - | --------------------------------------------------------- | -------- | ------ |
| 1 | Unique node ids                                              | duplicate rejected | PASS |
| 2 | Referential integrity                                             | unknown source/target rejected (2 cases) | PASS |
| 3 | Directionality (inherited from `Connection`)                          | inherited, verified | PASS |
| 4 | Port compatibility (inherited from `Connection`)                          | inherited, verified | PASS |
| 5 | No duplicate connections                                                     | duplicate rejected | PASS |
| 6 | Fan-in ≤ 1 per input port                                                       | shared target port rejected; different target ports on same node allowed | PASS |
| 7 | Fan-out unrestricted                                                               | shared source, multiple targets, all allowed | PASS |
| 8 | Acyclic                                                                               | 2-node, 3-node, disconnected cycles rejected; 4-node linear chain allowed | PASS |
| 9 | No dangling connections after removal                                                    | `remove_node` raises if referenced | PASS |

```
invariant_count: 9
case_count: 21
error_count: 0
expected_outcome_accuracy: 1.0
```

## The two corrections applied before and during implementation

1. **`GraphNode.id` is graph-local identity, not an architecture
   path.** The Staff review flagged that coupling `GraphNode.id` to
   `ArchitectureNode.id` (ADR-012's dotted `named_modules()` path)
   would silently break under an unrelated `Module`-tree refactor. The
   implemented contract accepts any non-empty string, with no read of
   or dependency on `inspection.py` — proven by a dedicated test
   constructing a `GraphNode` with an id that matches no real `Module`
   path at all.
2. **Recursive DFS cycle detection failed at scale.** The first
   implementation of `_has_cycle()` used recursive DFS. Running the
   Step 12 benchmark at 1,000 nodes (a linear chain) raised
   `RecursionError` — Python's default recursion limit is 1,000, and a
   1,000-node chain recurses exactly that deep. Fixed by rewriting
   `_has_cycle()` as an **iterative** Kahn's-algorithm topological
   sort, which has no recursion depth dependent on graph size. This is
   the concrete evidence behind this project's standing practice of
   benchmarking at multiple scales (10/100/1,000 nodes) rather than
   trusting correctness proven only at a single small size — the bug
   was invisible in every unit test (all built with ≤4 nodes) and only
   surfaced under the benchmark's 1,000-node fixture.

## API quality

| Property                                                                       | Result |
| ----------------------------------------------------------------------------------- | ------ |
| Immutable value semantics: `add_node`/`add_connection`/`remove_node`/`remove_connection` each return a new graph, never mutate `self` | PASS |
| Deterministic iteration order, preserved across every operation                       | PASS |
| Compatibility/directionality logic not duplicated — inherited from `Connection`           | PASS |
| No `Component` conformance check on the `GraphNode` construction path (ADR-010 hot-path rule respected) | PASS |
| Public export parity: `CompositionGraph`/`GraphNode` present in both `ragtorch.core.__all__` and `ragtorch.__all__` | PASS |

## Functional results

38 new tests (32 unit in `tests/unit/core/test_composition.py` + 4
integration in `tests/integration/test_composition_graph.py`).
Combined with the pre-existing 258, total suite is 296.

| Invariant                                                                                       | Result |
| ----------------------------------------------------------------------------------------------- | ------ |
| `GraphNode`: valid construction, empty id rejected, immutable, value equality, id independent of any architecture path | PASS |
| All nine `CompositionGraph` canonical invariants (see matrix above)                                  | PASS |
| Immutability: `CompositionGraph`/`GraphNode` attribute assignment raises                                 | PASS |
| Functional update semantics across three chained operations (`g0`→`g1`→`g2`→`g3`), each prior graph independently verified unchanged | PASS |
| `remove_connection` returns a graph without that connection, original graph unaffected                       | PASS |
| Determinism: stable iteration order across repeated access, equal graphs iterate identically, add appends, remove preserves relative order | PASS |
| No component execution: `ExplodingComponent` never triggers across construction or any of the four graph operations | PASS |
| Retriever→Reranker→Generator chain constructs; fan-out to Reranker+Evaluator; fan-in to shared Generator input rejected; fan-in to distinct Fusion input ports allowed | PASS |
| No `get_type_hints`/`eval`/`exec` in `composition.py` (source inspection)                                        | PASS |
| No provider import in `composition.py` (AST-based check, reusing the established pattern)                            | PASS |

## Test results

```
pytest:        296 passed (258 pre-existing, unmodified + 38 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 24 source files
coverage:      99% overall; composition.py 100%
```

Also verified directly against Python 3.10 (`py -3.10`): 296/296
passed, mypy clean — both before and after the Kahn's-algorithm
rewrite.

## Performance

`benchmarks/step12_composition_graph.py`, Windows, Python 3.12.0,
local.

| Operation                                                    | p50 (µs) |
| ----------------------------------------------------------------- | -------- |
| `CompositionGraph` construction — 10 nodes                            | 39.3     |
| `CompositionGraph` construction — 100 nodes                               | 379.4    |
| `CompositionGraph` construction — 1,000 nodes                                 | 4446.5   |
| `add_node()` on a 100-node graph                                                  | 381.3    |
| `add_connection()` on a 100-node graph                                               | 378.8    |
| construction — duplicate connection (fails fast)                                         | 241.1    |
| construction — two-node cycle (fails after cycle check)                                      | 15.0     |

### Empirical scaling confirmation

| N growth | p50 growth | Linear would predict |
| -------- | ---------- | --------------------- |
| 10 → 100 | 9.7x | 10x |
| 100 → 1,000 | 11.7x | 10x |

Growth stays close to linear — confirming the O(N+E) design
empirically, not just by inspection. `add_node`/`add_connection` cost
roughly the same as full construction of a comparably-sized graph
(~380µs, dominated by re-running all nine validation passes on the new
tuple), since each functional update re-validates the resulting graph
from scratch rather than incrementally verifying only the delta — an
explicit, accepted tradeoff for correctness simplicity over marginal
performance, not silently absorbed (see Limitations). The two-node
cycle failure (15.0µs) is far cheaper than any valid construction,
confirming the fixed check order fails fast when the very first
invariant after referential integrity/duplicates is violated in a
minimal fixture.

## Compatibility review

| Existing API                                       | Step 12 effect |
| ------------------------------------------------------ | -------------- |
| `Component`                                               | none — zero lines touched |
| `Module`/`Sequential`                                          | none — zero lines touched |
| `ExecutionEngine`/`ExecutionContext`                                | none — zero lines touched |
| `ArchitectureSnapshot`/`ArchitectureChild`/`validate_snapshot()`        | none — zero lines touched |
| `InputPort`/`OutputPort`/`is_compatible()`/`check_connection()`             | none — zero lines touched |
| `Connection`                                                                    | none — zero lines touched |
| existing exceptions                                                                 | unchanged — `ValidationError` reused, no new type |

All 258 pre-existing tests pass **unmodified**.

## Security review

| Question                                                          | Answer |
| ---------------------------------------------------------------------- | ------ |
| Does `CompositionGraph` execute any component?                             | No — proven by `ExplodingComponent` test across construction and every operation |
| Does it evaluate annotations or use reflection?                                | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Does it import any provider/model dependency?                                      | No — verified by AST-based import inspection |
| Does it inspect arbitrary component state?                                             | No — reads only `GraphNode.id` and `Connection`'s already-validated fields |
| Does `GraphNode` require `Component` conformance checking at construction?                 | No — deliberately, per ADR-010's hot-path prohibition |

## Dependency review

Zero new runtime dependencies. `composition.py` imports
`ragtorch.core.component`, `ragtorch.core.connection`,
`ragtorch.core.errors` (all existing internal modules) plus the
standard library `dataclasses` — no `networkx`, no other graph
library. Confirmed via the AST-based import inspection test.

## Diff review

Scope: `src/ragtorch/core/composition.py` (new), `core/__init__.py` +
top-level `__init__.py` (export, 100%-parity convention),
`test_composition.py` (new), `test_composition_graph.py` (new),
`test_public_api.py` (2 entries), `benchmarks/step12_composition_graph.py`
(new), ADR-016 (new, corrected pre-implementation and mid-implementation,
to be accepted post-CI), requirements matrix (A52+, pending). No touch
to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`architecture.py`, `inspection.py`, `ports.py`, or `connection.py` —
confirmed by `git diff --stat main...HEAD`.

## Limitations (explicitly named, not silently absorbed)

- **Functional updates re-validate the entire graph, not just the
  delta.** `add_node`/`add_connection`/`remove_node`/`remove_connection`
  each construct a new `CompositionGraph`, which re-runs all nine
  `__post_init__` checks against the full node/connection set —
  O(N+E) per update, not O(1) or O(log N). Measured (`add_node`/
  `add_connection` on a 100-node graph cost ~380µs, comparable to
  building that graph from scratch) rather than assumed cheap. Accepted
  as a deliberate simplicity-over-performance tradeoff for this step;
  if a future workload demonstrates this is a real bottleneck at
  larger scale, an incremental-validation optimization is additive,
  not a contract change.
- **No `Block` type.** This step proves the validated aggregate in
  isolation; a future `Block`/execution-planning layer is expected to
  consume `CompositionGraph`, not built here.
- **No integration with `ArchitectureSnapshot`/`validate_snapshot()`.**
  Containment and data-flow composition remain independent concepts,
  per ADR-012's own non-goal.
- **No fan-in override mechanism.** The fan-in ≤ 1 default is not
  configurable in this version; a future explicit multi-input
  aggregation mechanism is deliberate, separate future work.
- **`GraphNode.component` is unchecked at construction.** No
  `isinstance(component, Component)` — deliberately, per ADR-010.

## Decision

**Step 12 Definition of Done: met locally** (Python 3.10 and 3.12 both
verified, before and after the Kahn's-algorithm fix). Per the
project's standing discipline, ADR-016's status change from Proposed
to Accepted is deferred until real GitHub Actions CI confirmation —
not claimed from local checks alone.
