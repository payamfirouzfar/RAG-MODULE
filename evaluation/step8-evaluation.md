# Step 8 Evaluation — Architecture Snapshot & Inspection

Date: 2026-08-16

Branch: `feat/step7-component-ports` (Step 8 built on the intended
post-Step-7 state; PR #3 remains open and unmerged per the project's
explicit-approval merge policy)

## Scope

Framework/architecture feature, not RAG quality. Per ADR-012, this
evaluation proves: can a `Module` tree's structure be captured as one
immutable, deterministic, side-effect-free snapshot, consumed by
`inspect()` rather than re-walked independently — the concrete fix for
R8/A9 ("architecture inspection has one source of truth").

## Contract

- `ArchitectureNode(id, name, component_type, input_ports=(), output_ports=())`
- `ArchitectureChild(parent_id, child_id)` — tree containment only, never
  a data-flow edge.
- `ArchitectureSnapshot(nodes, children)` — immutable, tuple-based.
- `snapshot(module) -> ArchitectureSnapshot` and `Module.snapshot()`
  (thin delegation).
- `Module.inspect()` internally consumes `snapshot()`; its public string
  output is unchanged.

## Deterministic evaluation matrix

| Case              | Expected             | Result |
| ----------------- | --------------------- | ------ |
| Empty module (leaf) | 1 node, 0 children       | PASS |
| One-level parent (2 children) | 3 nodes, 2 children pairs  | PASS |
| Nested tree (grandparent → parent → 2 children) | exact dotted-path IDs matching `named_modules()`  | PASS |
| Repeated snapshot of equivalent trees | `snapshot_a == snapshot_b`  | PASS |
| Ports absent | `input_ports == () and output_ports == ()`  | PASS |
| Secret instance state (`api_key`, `password`) | not present anywhere in the snapshot or its repr  | PASS |
| Data-flow inference | never present — only parent→child pairs, no sibling-to-sibling relationships  | PASS |
| `inspect()` on a realistic pipeline | backward-compatible: `"Modules: N"`, `"Depth: N"`, `"name (Type)"` lines unchanged | PASS |

```
case_count: 8
error_count: 0
exact_match: 8/8
```

## Functional results

38 new tests (20 unit in `tests/unit/core/test_inspection.py` + 3
integration in `tests/integration/test_architecture_snapshot.py`, plus
2 additional security/provider-independence unit tests folded into the
same file — 20 total unit + 3 integration = 23 new; combined with the
pre-existing 179, total suite is 202).

| Invariant                                                                 | Result |
| ------------------------------------------------------------------------------ | ------ |
| `ArchitectureNode`/`ArchitectureChild`/`ArchitectureSnapshot` construct correctly | PASS |
| All three are immutable (frozen dataclass — assignment raises)                       | PASS |
| Ports default to `()`                                                                    | PASS |
| Node IDs are byte-for-byte identical to `named_modules()`'s own output                       | PASS |
| Tree children are correctly derived (parent→child pairs)                                        | PASS |
| Nested (multi-level) children relationships are correct                                             | PASS |
| No sibling-to-sibling ("data-flow") relationship ever appears                                          | PASS |
| Two snapshots of equivalent trees are `==`                                                                | PASS |
| Node ordering is deterministic across repeated calls                                                        | PASS |
| `Module.snapshot()` matches the free function `snapshot(module)`                                                | PASS |
| A component whose `__call__`/`forward` raises `AssertionError` if invoked still snapshots successfully | PASS |
| A component with `self.api_key`/`self.password` never leaks them into the snapshot repr                    | PASS |
| No `get_type_hints`/`eval`/`exec` in `inspection.py` (verified by source inspection)                            | PASS |
| No provider import in `inspection.py` (AST-based check, reusing the Step 7 pattern)                                | PASS |
| `inspect()` output unchanged for a realistic multi-component pipeline                                                  | PASS |
| `snapshot()` over a `Sequential` composite produces the expected step nodes                                              | PASS |

## A real bug caught and fixed before commit (not shipped)

The first implementation of `snapshot()` used three separate
`named_modules()` walks (one to build a `path_by_module` lookup, one for
nodes, one for children) — correct but needlessly expensive. Optimizing
this to derive child IDs by string concatenation
(`f"{node_id}.{child_name}"`) introduced a **real correctness bug**: for
a *root* module, `named_modules()`'s own logic starts its internal
`prefix` as `""`, so a root's direct children get bare names
(`"child_a"`), not `"{root_name}.child_a"` — but my hand-rolled
reconstruction used the root's own `node_id` (non-empty) as the prefix,
producing `"Parent.child_a"` instead of the correct `"child_a"`.

Caught by manually re-verifying the optimization's output against
`named_modules()` directly (not just re-running the existing test
suite, which — notably — still passed 202/202 with the bug present,
because the affected assertions checked `snap.nodes` IDs, which come
straight from `named_modules()` and were correct, not `snap.children`'s
`child_id` field, which was wrong). This is recorded because it's a
reminder that passing tests are not proof of correctness for a change
the tests weren't specifically written to catch — the fix was verified
by manual output inspection against the ADR's own stated invariant
("node ids are byte-for-byte the same dotted paths `named_modules()`
already produces"), not merely by rerunning `pytest`.

**Fix**: reverted to two `named_modules()` passes (down from three) —
one to build both `nodes` and an `id(object) -> dotted-path` lookup
dict, one to build `children` using that lookup rather than
reconstructing paths by hand. Verified correct against nested trees
(`Grandparent` → `Parent` → `child_a`/`child_b`) by direct inspection,
not just re-running tests.

## Test results

```
pytest:  202 passed (179 pre-existing, unmodified + 23 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 21 source files
coverage:      99% overall; inspection.py 100%
```

Also verified directly against Python 3.10 (`py -3.10`), per the Step 7
lesson that local-only testing on one interpreter is insufficient:
202/202 passed, mypy clean. One **pre-existing, unrelated** flaky test
(`test_latency_measure_records_elapsed_time` — a `time.sleep(0.01)`
timing assertion, `>= 10ms` measured at `9.62ms` once) was observed on
3.10 and confirmed to pass in isolation; it predates this step (last
touched in the original Step 2 evaluation-primitives commit) and is
unrelated to any Step 8 change — noted here rather than silently
"fixed" outside this step's scope.

## Performance

`benchmarks/step8_architecture_snapshot.py`, Windows, Python 3.12.0,
local, post-fix numbers.

| Operation                                                   | p50 (µs) |
| ------------------------------------------------------------------ | -------- |
| `snapshot()` — empty module                                            | 7.1      |
| `snapshot()` — 10-module tree                                              | 67.4     |
| `snapshot()` — 100-module tree                                                | 626.2    |
| `inspect()` — 10-module tree (snapshot-backed)                                    | 100.0    |

### A real, honestly-reported regression on `inspect()`

Step 1's original benchmark measured `inspect()` at **~13.4µs p50** on
an 11-module tree. This step's snapshot-backed `inspect()` measures
**~100µs p50** on a comparably-sized (10-module) tree — roughly **7x**
higher. This is not a bug: isolating the cost showed `named_modules()`
alone (the same tree walk the old `inspect()` also did) costs ~10µs;
the remaining ~57-90µs is the cost of constructing 10-100+ frozen
`ArchitectureNode`/`ArchitectureChild` dataclass instances that the old
string-building implementation never allocated (it wrote directly into
a `list[str]`).

This is judged an **acceptable, deliberate tradeoff**, not silently
absorbed:

- `inspect()` is a diagnostic/introspection method, never on any
  execution hot path (`Module.__call__`, `ExecutionEngine.execute`,
  `Sequential.forward` are all completely unchanged by this step —
  confirmed by diff).
- The entire point of ADR-012 is trading a cheap, throwaway string-walk
  for a reusable, immutable, typed intermediate representation that
  every future renderer/serializer/graph-consumer can share — that
  representation has a real construction cost, and pretending otherwise
  would misrepresent what the design actually does.
- At 100µs even for a 10-module tree, this remains 3-4 orders of
  magnitude below any real RAG operation (embedding calls, LLM
  generation, vector search all run in milliseconds-to-seconds) — the
  same reasoning applied to accept small framework overheads in Steps
  3-7's benchmarks.

No regression exists on any hot path: `Module(input)` and `Sequential`
execution are untouched by this step (not re-benchmarked here since
nothing in their code changed — see Compatibility review).

## Compatibility review

| Existing API        | Step 8 effect |
| -------------------- | -------------- |
| `Component`          | none — zero lines touched |
| `Module.__call__`    | none — zero lines touched |
| `Sequential`         | none — zero lines touched |
| `ExecutionEngine`    | none — zero lines touched |
| `ExecutionContext`   | none — zero lines touched |
| `ports.py`           | read-only consumption (`ArchitectureNode.input_ports`/`output_ports` reference `InputPort`/`OutputPort` types; `ports.py` itself unmodified) |
| `Module.inspect()`   | implementation changed (now snapshot-backed); output string format unchanged — existing test `test_inspect_contains_counts_and_tree` passes unmodified |
| `named_modules()`    | unchanged; now has a second consumer (`snapshot()`) alongside `inspect()`'s old direct use |
| existing exceptions  | unchanged — no new exception type introduced |

All 179 pre-existing tests pass **unmodified**.

## Security review

| Question                                    | Answer |
| ------------------------------------------------ | ------ |
| Does `snapshot()` execute any component?              | No — `ExplodingComponent` test proves a component whose `__call__`/`forward` raises if invoked still snapshots successfully |
| Does `snapshot()` read arbitrary instance state?          | No — only `module.name`, `module.component_type`, `named_children()` are read; `SecretModule` test proves `self.api_key`/`self.password` never appear in the snapshot or its repr |
| Are annotations evaluated?                                    | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Are ports auto-discovered from arbitrary attributes?              | No — `ArchitectureNode.input_ports`/`output_ports` default to `()`; no discovery mechanism exists or was added |

## Dependency review

Zero new dependencies. `inspection.py` imports only `dataclasses`
(stdlib), `typing` (stdlib, `TYPE_CHECKING`), and
`ragtorch.core.ports` (existing internal module, for the
`InputPort`/`OutputPort` type references on `ArchitectureNode`).
Confirmed via AST-based import inspection test
(`test_inspection_module_has_no_provider_dependencies`), reusing the
Step 7 pattern rather than a naive substring scan.

## Future-change check (per the project's own Staff-rule framing)

| Question                             | Answer |
| ----------------------------------------- | ------ |
| Can the renderer be replaced?                  | Yes — `inspect()` is the only consumer today; a JSON/Mermaid renderer would be a new function consuming the same `ArchitectureSnapshot`, not a change to it |
| Can JSON serialization be added later?             | Yes — deferred deliberately (ADR-012 Non-goals), not designed prematurely |
| Can data-flow/graph edges be added later?              | Yes — `ArchitectureChild` is explicitly *not* named `ArchitectureEdge`, keeping that name free for a real future data-flow type |
| Can ports evolve?                                          | Yes — `input_ports`/`output_ports` exist in the shape now, empty by default, ready for a future population mechanism |
| Does `snapshot()` execute the model?                           | No — proven by test, not merely claimed |
| Does this require a provider?                                      | No |

## Diff review

Scope: `src/ragtorch/core/inspection.py` (new), `src/ragtorch/core/module.py`
(inspect() migrated to be snapshot-backed; snapshot() delegation added;
zero other lines in the class changed), `core/__init__.py` + top-level
`__init__.py` (export, 100%-parity convention), `test_inspection.py`
(new), `test_architecture_snapshot.py` (new), `test_public_api.py`
(4 entries added), `benchmarks/step8_architecture_snapshot.py` (new),
ADR-012 (new, finalized before implementation, to be accepted post-CI),
requirements matrix (A21+). No touch to `Component`, `ExecutionEngine`,
`ExecutionContext`, `Sequential`, `ports.py`, or any provider file.

## Decision

**Step 8 Definition of Done: met locally** (Python 3.10 and 3.12 both
verified). Per the project's standing discipline, ADR-012's status
change from Proposed to Accepted is deferred until real GitHub Actions
CI confirmation on the pushed branch/PR — not claimed from local
checks alone. Data-flow edges, port auto-discovery, serialization,
and additional renderers (JSON, Mermaid) remain explicit, named future
work per ADR-012 Non-goals, not silently implied as imminent.
