# Step 13 Evaluation — Execution Plan

Date: 2026-08-16

Branch: `feat/step13-execution-plan-implementation`, forked from
`feat/step13-execution-plan` (PR #8, docs-only ADR-017 + A65) after
that branch's 13B.5 adversarial review returned PASS, based on `main`
after PR #7 (Step 12) was merged with explicit approval.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-017, this
evaluation proves: given a valid `CompositionGraph`, does `plan()`
correctly derive a deterministic, dependency-respecting `ExecutionPlan`
— with FIFO Kahn's-algorithm ordering (not the LIFO shape
`CompositionGraph._has_cycle()` uses), no component execution, no
graph mutation or retention, and no `ExecutionEngine` dependency — as
a static, structural fact, independent of how or whether the plan is
ever executed.

## The adversarial review that shaped this implementation

Unlike every prior step, ADR-017 went through **two rounds of
adversarial review before any code was written**, and both rounds
found real defects that would have shipped silently if implementation
had proceeded from the first draft:

- **13B.3 finding ADV-01 (BLOCKER)**: the ADR's first draft claimed
  `plan()` reuses "the same iterative Kahn's-algorithm shape"
  `CompositionGraph._has_cycle()` uses, and that ties break by
  `graph.nodes` declaration order. Direct construction proved this
  false: `_has_cycle()`'s ready queue is LIFO (`list.pop()`), and on
  the diamond `A→B, A→C, B→D, C→D` declared `(A,B,C,D)`, that shape
  visits `A, C, B, D` — reversing `B`/`C`. Corrected to an explicit
  FIFO `collections.deque` before implementation began.
- **13B.5 finding ADV-04 (MINOR, found re-attacking the corrected
  claim)**: even the FIFO correction's "graph.nodes declaration order"
  claim was imprecise — true only for nodes ready at the start of
  planning. Nodes that become ready mid-traversal are ordered by
  `graph.connections` discovery order instead. Both orderings are
  deterministic; conflating them into one claim would have misled a
  future reader who tested only the time-zero case.

Both findings are directly reflected in this implementation's test
suite (`test_ready_node_tie_break_uses_graph_node_declaration_order`
for ADV-01, `test_mid_traversal_ties_follow_connection_declaration_order`
and `test_mid_traversal_tie_break_is_independent_of_graph_nodes_order`
for ADV-04) — these are not generic correctness tests, they are
regression guards for specific bugs caught before they could exist in
committed code.

## Contract

```python
ExecutionStep(node_id: str, dependencies: tuple[str, ...])
ExecutionPlan(steps: tuple[ExecutionStep, ...])
plan(graph: CompositionGraph) -> ExecutionPlan
```

`plan()` builds an adjacency list and in-degree map from
`graph.connections` in one O(E) pass, then runs Kahn's algorithm with
an explicit `collections.deque` FIFO ready queue. No revalidation of
graph structure (trusts `CompositionGraph`'s existing guarantees). No
`component.__call__` is ever invoked. No reference to `graph` is
retained. `ExecutionPlan` does not implement `__iter__`/`__len__`/
`__getitem__` — callers use `plan.steps` directly.

## Correctness

| Invariant                                                          | Expected | Result |
| ---------------------------------------------------------------------- | -------- | ------ |
| Empty graph                                                                 | empty plan | PASS |
| Single node                                                                     | single step, no dependencies | PASS |
| Linear chain                                                                       | correct order | PASS |
| Diamond (valid topological order)                                                     | `A` before `B`/`C`, both before `D` | PASS |
| Disconnected graph                                                                        | both components ordered independently | PASS |
| Dependencies are direct predecessors only (`A→B→C`: `C.dependencies == ("B",)`)              | PASS | PASS |
| Root node has empty dependencies                                                                | PASS | PASS |
| Diamond dependencies contain both predecessors, in connection declaration order                    | PASS | PASS |
| **E11a**: time-zero ties follow `graph.nodes` order (both directions tested)                            | PASS | PASS |
| **E11b**: mid-traversal ties follow `graph.connections` discovery order, independent of `graph.nodes` order | PASS | PASS |
| Repeated planning is deterministic                                                                            | PASS | PASS |
| Equal graphs produce equal plans                                                                                  | PASS | PASS |
| Differing plans are not equal                                                                                        | PASS | PASS |

```
invariant_count: 13
case_count: 33
error_count: 0
expected_outcome_accuracy: 1.0
```

## API quality

| Property                                                                                     | Result |
| ------------------------------------------------------------------------------------------------- | ------ |
| No re-implementation of graph validity — `plan()` trusts `CompositionGraph`'s existing guarantee      | PASS |
| `ExecutionPlan` has no `graph`-typed field (introspected via `dataclasses.fields`, not `__dict__`)        | PASS |
| `ExecutionStep` has no `component`/`GraphNode`-typed field                                                    | PASS |
| Snapshot semantics: a plan is unaffected by later operations on its source graph                                  | PASS |
| Immutability: frozen dataclasses, tuple fields                                                                        | PASS |
| `ExecutionPlan` does not implement the iteration protocol (explicit test, not assumed from `frozen=True`)                | PASS |
| Public export parity: `ExecutionPlan`/`ExecutionStep`/`plan` present in both `ragtorch.core.__all__` and `ragtorch.__all__` | PASS |

## Functional results

33 new tests (28 unit in `tests/unit/core/test_execution_plan.py` + 5
integration in `tests/integration/test_execution_plan_composition.py`
— named to avoid a pytest module-basename collision with the unit test
file in this repository's rootless test layout). Combined with the
pre-existing 296, total suite is 329.

| Invariant                                                                                                                   | Result |
| --------------------------------------------------------------------------------------------------------------------------------- | ------ |
| No component execution: `ExplodingComponent` never triggers during `plan()`, single-node and chain cases                              | PASS |
| No `ExecutionEngine` import (AST-based check — distinct from the general provider-independence check)                                     | PASS |
| No provider import (AST-based, reusing the established pattern)                                                                                | PASS |
| No `get_type_hints`/`eval`/`exec` in `execution_plan.py`                                                                                           | PASS |
| Retriever→Reranker→Generator chain plans in order with correct dependencies                                                                            | PASS |
| Fan-out graph (Retriever→Reranker, Retriever→Evaluator) plans with both downstream steps depending only on Retriever                                       | PASS |
| Fusion node with two distinct input ports plans with both producers as dependencies, in declaration order                                                      | PASS |

## Test results

```
pytest:        329 passed (296 pre-existing, unmodified + 33 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 25 source files
coverage:      99% overall; execution_plan.py 100%
```

Also verified directly against Python 3.10 (`py -3.10`): 329/329
passed, mypy clean.

## Performance

`benchmarks/step13_execution_plan.py`, Windows, Python 3.12.0, local.

| Operation                                          | p50 (µs) |
| ------------------------------------------------------- | -------- |
| `plan()` — linear chain, 10 nodes                            | 8.9      |
| `plan()` — linear chain, 100 nodes                               | 74.9     |
| `plan()` — linear chain, 1,000 nodes                                 | 855.4    |
| `plan()` — linear chain, 10,000 nodes                                    | 12053.7  |
| `plan()` — wide fan-out, 10 nodes                                            | 8.5      |
| `plan()` — wide fan-out, 100 nodes                                               | 73.0     |
| `plan()` — wide fan-out, 1,000 nodes                                                 | 809.6    |
| `plan()` — wide fan-out, 10,000 nodes                                                    | 11309.3  |
| `plan()` — diamond-heavy, 20 nodes (4×5)                                                      | 22.9     |
| `plan()` — diamond-heavy, 60 nodes (4×15)                                                         | 127.6    |

### Observed scaling vs. the O(V+E) design target

A benchmark cannot mathematically prove an asymptotic complexity
bound; the table below reports what was measured, checked against
what linear growth would predict, not a proof that the algorithm is
O(V+E) — that claim rests on the algorithm's structure (one O(E) pass
to build adjacency/in-degree/dependency structures, one O(V+E) Kahn
traversal, no nested loop over nodes or connections anywhere in
`plan()`, confirmed by direct code inspection), with this benchmark
serving as a regression check against a future change accidentally
introducing quadratic behavior.

| N growth (linear chain) | p50 growth | Linear would predict |
| -------- | ---------- | --------------------- |
| 10 → 100 | 8.4x–8.8x (two independent runs) | 10x |
| 100 → 1,000 | 11.4x–12x | 10x |
| 1,000 → 10,000 | 14.1x–15.4x | 10x |

Growth stays close to linear through 1,000 nodes, with a modest
superlinear tail at 10,000 nodes in both independent runs — reported
as measured, not smoothed over; plausibly Python-level allocation/GC
overhead at that scale rather than an algorithmic defect, given the
structural argument above. No `RecursionError` or other
scale-dependent failure occurred at any tested size — unlike Step 12's
`_has_cycle()`, `plan()` used an iterative `deque`-based FIFO Kahn's
algorithm from its first implementation, so no equivalent bug was
possible to find.

## Compatibility review

| Existing API                                          | Step 13 effect |
| ----------------------------------------------------------- | -------------- |
| `Component`                                                    | none — zero lines touched |
| `Module`/`Sequential`                                              | none — zero lines touched |
| `ExecutionEngine`/`ExecutionContext`                                   | none — zero lines touched |
| `ArchitectureSnapshot`/`validate_snapshot()`                               | none — zero lines touched |
| `InputPort`/`OutputPort`/`is_compatible()`/`check_connection()`               | none — zero lines touched |
| `Connection`                                                                      | none — zero lines touched |
| `CompositionGraph`/`GraphNode`                                                       | none — zero lines touched (including `_has_cycle()`, whose LIFO shape was explicitly *not* changed — see "Ordering algorithm" in ADR-017) |
| existing exceptions                                                                     | unchanged — no new exception type introduced |

All 296 pre-existing tests pass **unmodified**.

## Security review

| Question                                                          | Answer |
| ---------------------------------------------------------------------- | ------ |
| Does `plan()` execute any component?                                       | No — proven by `ExplodingComponent` tests across single-node and chain construction |
| Does it evaluate annotations or use reflection?                                | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Does it import any provider/model dependency?                                      | No — verified by AST-based import inspection |
| Does it import `ExecutionEngine`?                                                       | No — verified by a dedicated AST-based check, distinct from the general provider check |
| Does it retain the source `CompositionGraph`?                                              | No — verified by introspecting `dataclasses.fields(ExecutionPlan)` |
| Can a plan carry a provider client, API key, or open resource?                                 | No — `ExecutionStep`/`ExecutionPlan` contain only `str` and tuples thereof, by construction |

## Dependency review

Zero new runtime dependencies. `execution_plan.py` imports
`ragtorch.core.composition` (`CompositionGraph`) and the standard
library `collections`/`dataclasses` — no `networkx`, no scheduler
package, no serialization framework. Confirmed via the AST-based
import inspection tests.

## Diff review

Scope: `src/ragtorch/core/execution_plan.py` (new), `core/__init__.py`
+ top-level `__init__.py` (export, 100%-parity convention),
`test_execution_plan.py` (new), `test_execution_plan_composition.py`
(new), `test_public_api.py` (3 entries),
`benchmarks/step13_execution_plan.py` (new), ADR-017 (already accepted
via PR #8's separate docs-only review — see that PR's own evidence
trail), requirements matrix (A65, evidence updated). No touch to
`Component`, `Module`, `Sequential`, `ExecutionEngine`,
`architecture.py`, `inspection.py`, `ports.py`, `connection.py`,
`composition.py` (including `_has_cycle()`) — confirmed by
`git diff --stat main...HEAD`.

## Limitations (explicitly named, not silently absorbed)

- **No executor.** `ExecutionPlan` is data; nothing consumes it yet.
  This is the deliberate scope boundary this step exists to establish
  — see ADR-017 Non-goals.
- **No `ExecutionEngine` integration.** `plan()` and `ExecutionEngine`
  remain entirely independent; wiring them together is explicit future
  work.
- **No parallel/async execution representable beyond dependency data.**
  `ExecutionStep.dependencies` is sufficient for a future scheduler to
  derive readiness, but no grouped/leveled representation is computed
  or exposed in this version.
- **No serialization.** The data model is kept serialization-friendly
  (no runtime objects) without implementing serialization itself.
- **Two distinct tie-break rules, not one uniform rule.** Time-zero
  ties follow `graph.nodes` order; mid-traversal ties follow
  `graph.connections` discovery order. Both are deterministic, but a
  future reader must not assume a single ordering source governs all
  ties — this is documented explicitly in ADR-017 precisely because
  the first draft's imprecision (ADV-04) could otherwise recur.

## Decision

**Step 13 implementation Definition of Done: met locally** (Python
3.10 and 3.12 both verified). Per the project's standing discipline,
this evidence is submitted for real CI confirmation before the
requirements matrix or any status is claimed as final — not from local
checks alone.
