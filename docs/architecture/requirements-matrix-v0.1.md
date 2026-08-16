# RAG-MODULE v0.1 Requirements Matrix

This matrix converts the frozen requirements into verifiable engineering obligations and adds the architectural requirements introduced by the v0.1 direction.

| ID | Requirement | Current evidence | Gap | Planned verification |
|---|---|---|---|---|
| R1 | Vendor independence | ADR-005; no provider runtime dependency | Provider contracts not yet implemented | import/core isolation tests |
| R2 | Model independence | Provider-independence ADR | No model contract yet | provider contract tests |
| R3 | Storage independence | Requirement frozen | No storage contract yet | adapter contract tests |
| R4 | Observability independence | local Trace/Metrics/logging + execution-scoped Events | Provider integrations not yet implemented | event/adapter isolation tests |
| R5 | Evaluation first | evaluation package + step reports | Architecture evaluation contract still evolving | per-feature scorecard |
| R6 | Replaceability | Module contract | Future Component/Port contracts needed | contract compatibility tests |
| R7 | Composability | Module registration + Sequential | No general Block/Graph model | composition contract tests |
| R8 | Inspectability | Module.inspect()/repr() | No structured architecture snapshot | snapshot tests |
| R9 | Reproducibility | ExecutionContext + evaluation metadata | Run artifact schema incomplete | deterministic metadata tests |
| R10 | Security by default | redaction + sensitive-key detection | Need architecture snapshot secret policy | secret exclusion tests |
| R11 | Optional dependencies | pyproject extras direction | Provider extras not yet implemented | dependency/import CI |
| R12 | Backward compatibility | public API contract test | Migration strategy for Component missing | API contract suite |
| R13 | Performance budgets | Step 1-4 benchmarks + Step 5 benchmark protocol | Post-fix CI baseline must be collected before a hard threshold is introduced | benchmark artifact + controlled regression comparison |
| R14 | Local-first | current core is offline | Future providers must preserve offline core | offline CI path |
| R15 | Cloud-optional | no cloud requirement | Future enterprise layer undefined | packaging/import boundary tests |
| A1 | Component is the stable conceptual unit | ADR-010; `ragtorch.core.component.Component` structural protocol | Ports/Blocks/Architecture built on top of Component not yet designed | contract tests (`tests/unit/core/test_component.py`) |
| A2 | Blocks compose Components | Sequential exists | Block abstraction not yet formalized | nested composition tests |
| A3 | Architectures are user-defined | RAGModule marker exists | RAGModule semantics too weak | architecture contract |
| A4 | Runtime is separate from business logic | ExecutionEngine exists | Runtime ownership boundaries need formalization | engine/component integration tests |
| A5 | Explicit execution identity | ExecutionContext + execution-scoped Events | EventBus must eventually become execution-scoped for isolation | event identity tests + future concurrency tests |
| A6 | Provider routing is policy-driven | only provider ADR | Router/fallback absent | future policy tests |
| A7 | Local-only fallback is enforceable | local-first requirement | no routing layer | future security/policy tests |
| A8 | Evaluation can gate runtime behavior | evaluation is post-execution today | quality-gate policy absent | future routing evaluation |
| A9 | Architecture inspection has one source of truth | string inspect exists | no structured snapshot | snapshot contract tests |
| A10 | No global mutable execution state | explicit context + no global current-context mechanism | process-wide EventBus remains as compatibility delivery mechanism | future execution-scoped delivery tests |
| A11 | Core remains dependency-light | core has no provider dependency | future plugins not yet separated | import graph/packaging tests |
| A12 | Every major feature has tests + benchmark + evaluation | established through Step 4 and Step 5 benchmark/CI | must continue | milestone checklist |
| A13 | Component contract is provider-agnostic and structural | ADR-010; `Component` is a `@runtime_checkable Protocol` with `name`/`component_type`/`__call__` only | none for the minimal contract as scoped | `test_non_module_object_can_satisfy_component_protocol`, `test_incomplete_object_does_not_satisfy_component_protocol` |
| A14 | Module compatibility without inheritance migration | `Module.name`/`Module.component_type` properties; zero call-site changes | none | `test_module_subclass_satisfies_component_protocol`; full existing 148-test suite unmodified |
| A15 | External implementations satisfy Component without a Module/ragtorch dependency | `ExternalComponent`/`IntToStringComponent` test doubles satisfy `Component` with no inheritance | none for Step 6 scope; real third-party components (Retriever, etc.) not yet built | `test_non_module_object_can_satisfy_component_protocol` |
| A16 | Component conformance checks never occur on a hot execution path | ADR-010 hard rule; no `isinstance(..., Component)` in `Module.__call__`/`ExecutionEngine.execute`/`Sequential.forward` | enforcement is currently a documented rule + code review, not an automated lint/architecture-test | `benchmarks/step6_component_contract.py` documents the real cost (~0.3us) informationally; no automated guard yet |
| A17 | Port metadata is immutable and its type must be a real Python class | ADR-011; `InputPort`/`OutputPort` are frozen dataclasses, `__post_init__` rejects non-class `type` via `ValidationError` | none for the scoped contract | `test_input_port_is_immutable`, `test_input_port_rejects_non_class_type`, `test_input_port_rejects_generic_alias` |
| A18 | Port compatibility is explicit, deterministic, and conservative (exact/subtype only) | ADR-011; `is_compatible()` = `issubclass(output.type, input.type)` | generic/`Union`/structural compatibility not supported — explicit non-goal until a real component demonstrates need | `test_exact_types_are_compatible`, `test_subtype_is_compatible_with_supertype`, `test_supertype_is_not_compatible_with_subtype`, `test_unrelated_types_are_incompatible` |
| A19 | Port metadata is never derived from `__call__` annotations via reflection | ADR-011 security-motivated design; verified `typing.get_type_hints()` evaluates string annotations before deciding | none — this is a permanent constraint, not a gap | `test_ports_module_does_not_use_annotation_evaluation` (source-inspection test) |
| A20 | Ports remain optional, external metadata — not part of the `Component` contract | ADR-011 Non-goals; `Component`'s three members unchanged since ADR-010 | `Component` gaining `input_ports`/`output_ports` is future work once a real component justifies the shape | full existing Component test suite unmodified; `ports.py` has zero import relationship to `component.py` |
| A21 | Canonical architecture snapshot — one source of truth for architecture structure | ADR-012; `ragtorch.core.inspection.ArchitectureSnapshot` built by `snapshot()`, consumed by `inspect()` rather than a second independent tree walk | no serializer/renderer beyond `inspect()`'s text form yet — explicit non-goal until a real consumer needs one | `test_snapshot_matches_actual_module_hierarchy`, `test_inspect_output_unchanged_for_realistic_pipeline` |
| A22 | Deterministic node identity | ADR-012; `ArchitectureNode.id` reuses `named_modules()`'s existing dotted-path scheme — not `id()`, not a generated UUID | none for the scoped contract | `test_snapshot_uses_named_module_paths`, `test_snapshot_is_deterministic` |
| A23 | Snapshot is immutable | ADR-012; `ArchitectureNode`/`ArchitectureChild`/`ArchitectureSnapshot` are frozen dataclasses with tuple fields | none | `test_architecture_node_is_immutable`, `test_architecture_child_is_immutable`, `test_architecture_snapshot_is_immutable` |
| A24 | Structural child relationships only — no inferred data-flow edges | ADR-012 Non-goals; `ArchitectureChild` (deliberately not "Edge") represents tree containment only | data-flow/graph edges deferred until a real composition/graph contract exists (future step) | `test_snapshot_does_not_infer_data_flow_edges` |
| A25 | Ports on architecture nodes remain optional and are never auto-discovered | ADR-012; `ArchitectureNode.input_ports`/`output_ports` default to `()`; no `vars()`/`__dict__`/attribute-scanning discovery mechanism exists or was added | a future explicit port-supplying API is deferred, not designed yet | `test_architecture_node_defaults_to_empty_ports` |
| A26 | `inspect()` remains backward compatible after becoming snapshot-backed | ADR-012; `Module.inspect()`'s pre-existing string output (`"Modules: N"`, `"Depth: N"`, `"name (Type)"`) is unchanged | none — existing test passes unmodified | `test_inspect_contains_counts_and_tree` (Step 1, unmodified), `test_inspect_output_unchanged_for_realistic_pipeline` (Step 8) |
| A27 | Snapshot construction never executes a component | ADR-012; `snapshot()` reads only `name`/`component_type`/`named_children()`, never calls `module(...)` | none — this is a permanent constraint, not a gap | `test_snapshot_does_not_execute_components` (a component whose `__call__`/`forward` raises if invoked still snapshots successfully) |
| A28 | Snapshot construction never exposes arbitrary instance state | ADR-012; only known, intentional properties are read — never `vars()`/`__dict__` | none — stronger than a redaction filter: the state is structurally unreachable, not merely hidden after being read | `test_snapshot_does_not_expose_arbitrary_instance_state` (a component with `self.api_key`/`self.password` never leaks them) |
| A29 | Architecture snapshots are structurally validatable | ADR-013; `ragtorch.core.architecture.validate_snapshot()` — a non-empty-rooted-tree contract, `ValidationError` on the first violation, `None` on success | validated at the snapshot boundary only; no `Module.validate()` convenience method yet (deferred until repeatedly needed, mirroring `Module.snapshot()`'s own history) | `tests/unit/core/test_architecture.py` (19 tests), `tests/integration/test_architecture_validation.py` (3 tests) |
| A30 | Node identifiers are unique within a valid snapshot | ADR-013 Rule 2 | none | `test_duplicate_node_id_is_invalid` |
| A31 | A valid architecture contains exactly one root | ADR-013 Rule 6 | none | `test_multiple_roots_is_invalid`, `test_cycle_produces_zero_roots_is_invalid` |
| A32 | Each non-root node has exactly one parent | ADR-013 Rule 5 — proven insufficient to infer from root-count alone via a concrete diamond counter-example (`A→B`, `A→C`, `B→D`, `C→D`: one root, zero duplicate IDs, but `D` has two parents), verified by direct construction before being frozen into the ADR | none | `test_diamond_multiple_parents_is_invalid` |
| A33 | All nodes are reachable from the root | ADR-013 Rule 7 — proven to catch a disconnected cycle (`A→B` valid + `C→D→C`) that root-counting alone misses, verified by direct construction | none | `test_disconnected_node_is_invalid`, `test_disconnected_cycle_is_invalid` |
| A34 | A valid architecture is acyclic | ADR-013 — no separate cycle-detection algorithm; proven (not merely asserted) that Rules 2/5/6 catch a connected cycle via zero-roots, and Rule 7 catches a disconnected cycle | none — deliberately not implemented as a redundant separate DFS pass | `test_cycle_produces_zero_roots_is_invalid`, `test_disconnected_cycle_is_invalid` |
| A35 | Architecture validation is provider-independent | ADR-013; `architecture.py` imports only `ragtorch.core.errors`/`ragtorch.core.inspection` | none | `test_architecture_module_has_no_provider_dependencies` (AST-based, reusing the Step 7/8 pattern) |
| A36 | Architecture validation does not mutate the snapshot | ADR-013; read-only, no automatic repair/deduplication/reordering | none | `test_validation_does_not_mutate_snapshot` |
| A37 | A compatible port pair passes composition precondition checking | ADR-014; `ragtorch.core.ports.check_connection()`, `None` on success | none | `test_check_connection_returns_none_for_exact_types`, `test_check_connection_returns_none_for_compatible_subtype` |
| A38 | An incompatible port pair raises on composition precondition checking | ADR-014; `ValidationError` (reused, no new exception type) | none | `test_check_connection_raises_for_incompatible_types` |
| A39 | Composition precondition checking follows `is_compatible()`'s subtype rule exactly, with no separate compatibility logic | ADR-014; `check_connection()`'s body is exactly `if not is_compatible(...): raise ...` — verified by reading the implementation, not merely asserted | none — this is a permanent constraint, not a gap | `test_check_connection_returns_none_for_compatible_subtype`, plus the ADR-014 design rationale itself |
| A40 | `is_compatible()`'s existing `bool` contract is unchanged by the addition of `check_connection()` | ADR-014; explicit regression pair | none | `test_is_compatible_remains_true_for_valid_pair_after_check_connection_added`, `test_is_compatible_remains_false_for_invalid_pair_after_check_connection_added` |
| A41 | Composition precondition checking does not mutate either `Port` | ADR-014; both `Port` types are frozen dataclasses, re-asserted post-call | none | `test_check_connection_does_not_mutate_ports` |
| A42 | Composition precondition checking is deterministic across repeated calls, on both success and failure paths | ADR-014 | none | `test_check_connection_is_deterministic_across_repeated_calls` |
| A43 | The precondition-check error message identifies both port names and both type names | ADR-014 | none | `test_check_connection_error_contains_output_port_name`, `test_check_connection_error_contains_input_port_name`, `test_check_connection_error_contains_both_type_names` |
| A44 | Composition precondition checking is provider-independent | ADR-014; `ports.py` imports only `ragtorch.core.errors` (unchanged from Step 7) | none | `test_ports_module_has_no_provider_dependencies` (AST-based, now covering `check_connection()` too) |
| A45 | A single data-flow connection can be persisted as data, not merely checked in the moment | ADR-015; `ragtorch.core.connection.Connection`, a frozen value type | no collection/graph type holds multiple connections yet | `test_connection_constructs_for_compatible_ports` |
| A46 | Connection directionality is enforced at runtime, not merely by type annotation | ADR-015; explicit `isinstance` checks in `__post_init__` — a correction over the ADR's first draft, which assumed annotations alone were sufficient | none — this is a permanent constraint, not a gap | `test_connection_rejects_input_port_as_source`, `test_connection_rejects_output_port_as_target` |
| A47 | Connection node identifiers must be non-empty strings | ADR-015 | none | `test_connection_rejects_empty_source_node_id`, `test_connection_rejects_empty_target_node_id` |
| A48 | Connection compatibility checking delegates to `check_connection()`, never duplicates it | ADR-015; `Connection.__post_init__`'s final step is exactly `check_connection(self.source_port, self.target_port)` | none — this is a permanent constraint, not a gap | `test_connection_delegates_to_check_connection_not_duplicate_logic` (compares error messages, not just "both raise") |
| A49 | Connection has value equality and is hashable, with no synthetic identity | ADR-015; plain frozen `@dataclass`, consistent with `ArchitectureChild`'s existing precedent | a future mutable connection registry, if ever needed, would require reopening this decision | `test_equal_connections_have_value_equality`, `test_connection_is_hashable`, `test_equal_connections_hash_equally` |
| A50 | Connection places no fan-out/fan-in cardinality constraint | ADR-015; deliberately undecided, deferred to a future collection/`Block` type | cardinality rules not yet designed | `test_multiple_connections_may_share_source`, `test_multiple_connections_may_share_target` |
| A51 | Connection construction is provider-independent | ADR-015; `connection.py` imports only `ragtorch.core.errors`/`ragtorch.core.ports` | none | `test_connection_module_has_no_provider_dependencies` (AST-based, reusing the Step 7/10 pattern) |
| A52 | A collection of nodes and connections can be validated as a whole, not just pairwise | ADR-016; `ragtorch.core.composition.CompositionGraph` | none | `test_construction_succeeds_with_unique_node_ids`, `test_empty_graph_is_valid` |
| A53 | Composition node identifiers are unique within a graph | ADR-016 invariant 1 | none | `test_construction_rejects_duplicate_node_ids` |
| A54 | Every connection in a composition references nodes that actually exist in that graph | ADR-016 invariant 2 | none | `test_construction_rejects_connection_with_unknown_source`, `test_construction_rejects_connection_with_unknown_target` |
| A55 | Composition graph node identity is independent of architecture-tree path identity | ADR-016; `GraphNode.id` is graph-local, not derived from or coupled to `ArchitectureNode.id` (ADR-012) — a Staff-review correction applied before implementation | none — this is a permanent constraint, not a gap | `test_graph_node_id_is_independent_of_architecture_path` |
| A56 | Duplicate connections within a composition are rejected | ADR-016 invariant 5 | none | `test_construction_rejects_duplicate_connections` |
| A57 | A composition input port accepts at most one incoming connection (fan-in ≤ 1) | ADR-016 invariant 6; deliberately conservative — see ADR-016 for why aggregation semantics belong to a future explicit component, not the graph | a future explicit aggregation mechanism, if ever justified | `test_construction_rejects_fan_in_to_same_target_port`, `test_construction_allows_different_target_ports_on_same_node` (proves the rule is port-level, not node-level) |
| A58 | A composition output port may feed unlimited connections (fan-out unrestricted) | ADR-016 invariant 7 | none | `test_construction_allows_fan_out_from_same_source` |
| A59 | A composition graph must be acyclic | ADR-016 invariant 8; detected via an iterative Kahn's-algorithm topological sort — a recursive DFS first draft was caught failing at 1,000 nodes by this step's own benchmark and rewritten before commit | none — deliberately not the invariant for every future RAG-MODULE graph concept (e.g. a future `Loop` primitive is explicit higher-level future work, not an exception to this rule) | `test_construction_rejects_two_node_cycle`, `test_construction_rejects_three_node_cycle`, `test_construction_rejects_disconnected_cycle`, `test_construction_accepts_valid_linear_chain` |
| A60 | Removing a composition node cannot silently leave a dangling connection | ADR-016 invariant 9 | none | `test_remove_node_rejects_if_referenced_by_connection`, `test_remove_node_succeeds_when_unreferenced` |
| A61 | Composition graph operations are immutable — functional updates return a new graph, never mutate the original | ADR-016; consistent with every prior structural type's immutability guarantee in this codebase | functional updates re-validate the full graph rather than incrementally verifying only the delta — see `evaluation/step12-evaluation.md` Limitations | `test_add_node_returns_new_graph_without_mutating_original`, `test_chained_updates_preserve_each_intermediate_graph` |
| A62 | Composition graph iteration order is deterministic | ADR-016; `nodes`/`connections` are ordered tuples, not sets | none | `test_iteration_order_is_stable_across_repeated_access`, `test_equal_graphs_iterate_in_same_order`, `test_add_node_appends_new_node_last` |
| A63 | Composition graph construction and every operation never execute a component | ADR-016; no `component.__call__` is ever invoked | none — this is a permanent constraint, not a gap | `test_construction_never_executes_component`, `test_graph_operations_never_execute_component` (both use an `ExplodingComponent` that raises if invoked) |
| A64 | Composition graph construction is provider-independent | ADR-016; `composition.py` imports only `ragtorch.core.component`/`ragtorch.core.connection`/`ragtorch.core.errors` | none | `test_composition_module_has_no_provider_dependencies` (AST-based, reusing the established pattern) |
| A65 | A valid `CompositionGraph` can be transformed into a deterministic, immutable, dependency-aware `ExecutionPlan` without executing components, depending on `ExecutionEngine`, retaining runtime objects, or mutating/retaining the source graph | ADR-017; `src/ragtorch/core/execution_plan.py`; `plan(graph: CompositionGraph) -> ExecutionPlan`, FIFO Kahn's algorithm (`collections.deque`) — corrected during a two-round 13B.3/13B.5 adversarial review before implementation (ADV-01 BLOCKER: LIFO vs. FIFO queue discipline; ADV-04 MINOR: two distinct tie-break rules, not one) | none for the scoped contract; CI pending as the final proof step | `tests/unit/core/test_execution_plan.py` (28 tests), `tests/integration/test_execution_plan_composition.py` (5 tests), `benchmarks/step13_execution_plan.py` (10/100/1,000/10,000-node scaling, three shapes) |

## Step 5 status

Step 5's first implementation gap is now closed: the event-context overhead benchmark exists, the pre-fix observation is recorded, and CI executes and archives the benchmark for every supported Python version. The no-context execution path was also changed to avoid constructing execution-identity kwargs when no context is supplied.

The benchmark intentionally does **not** introduce an arbitrary hard microsecond threshold yet. A stable CI baseline must be collected first; then a justified regression budget can be added.

## Step 6 status

The Component contract (A1, A13-A16) is implemented per ADR-010:
`ragtorch.core.component.Component`, a minimal `@runtime_checkable Protocol`
with exactly `name`, `component_type`, and `__call__`. `Module` gains two
properties and structurally satisfies it with zero inheritance migration
and zero call-site changes anywhere in the existing 148 tests. An
independent, non-`Module` class also satisfies it, proving the contract is
genuinely structural rather than accidentally testing only `Module`.

`capabilities`, `configuration`, async/streaming variants, a component
registry, and Block/Architecture composition remain explicit non-goals for
this step (see ADR-010) — deferred until a real component exists to prove
their shape, not designed speculatively now.

## Step 7 status

Component ports (A17-A20) are implemented per ADR-011:
`InputPort`/`OutputPort` (frozen dataclasses, construction-time type
validation) and `is_compatible()` (single `issubclass()` check covering
both exact-match and subtype compatibility). `Component`, `Module`,
`ExecutionEngine`, `ExecutionContext`, and `Sequential` are all
unchanged — zero lines touched, all 159 pre-existing tests pass
unmodified. `ValidationError` (already existing) is reused; no new
exception type introduced. Ports are never derived from `__call__`
annotations via reflection — verified as a real code-execution surface
(`typing.get_type_hints()` evaluates string annotations) before
deciding against it, not assumed safe.

Generic-parameter-aware compatibility, `Union`/structural typing, ports
attached to `Component`, and a `Block`/graph builder that enforces
compatibility all remain explicit non-goals (see ADR-011) — deferred
until a real component demonstrates the need.

## Step 8 status

The architecture snapshot (A9, A21-A28) is implemented per ADR-012:
`ragtorch.core.inspection.ArchitectureSnapshot`, built by `snapshot()`
in a single logical pass over `Module.named_modules()`/`named_children()`
(one dict-building pass, one children-building pass — down from an
initial three-pass draft that both wasted work and, when "optimized" to
avoid the third pass by hand-reconstructing dotted paths, introduced a
real bug at the root level; caught before commit by verifying output
against `named_modules()` directly, not merely by re-running the
existing test suite, which still passed with the bug present since it
didn't specifically target that path). `Module.inspect()` is migrated to
render text from this snapshot rather than an independent walk of
`_modules` — its public string output is byte-for-byte unchanged
(existing Step 1 test passes unmodified). `Component`, `Module.__call__`,
`ExecutionEngine`, `ExecutionContext`, `Sequential`, and `ports.py` are
all unchanged — zero lines touched. `snapshot()` never executes a
component and never reads arbitrary instance state (`vars()`/`__dict__`)
— both proven by dedicated tests, not merely asserted.

A real, honestly-measured performance cost: `inspect()` is now ~100µs
p50 for a 10-module tree, versus Step 1's original ~13.4µs for an
11-module tree — roughly 7x higher, from constructing immutable
dataclass instances the old string-only implementation never allocated.
Accepted as a deliberate tradeoff (`inspect()` is diagnostic, never a
hot path; still 3-4 orders of magnitude below any real RAG operation),
not silently absorbed — see `evaluation/step8-evaluation.md` for the
full accounting.

Data-flow/graph edges, port auto-discovery, serialization (JSON/etc.),
and additional renderers (Mermaid/Graphviz) all remain explicit
non-goals (see ADR-012) — deferred until a real composition/graph
contract or consumer exists to justify their shape.

## Step 9 status

Architecture snapshot validation (A29-A36) is implemented per ADR-013:
`ragtorch.core.architecture.validate_snapshot()`, a ten-rule
non-empty-rooted-tree contract checked in a fixed order (empty →
duplicate IDs → dangling references → self-containment → multiple
parents → root count → reachability), `None` on success,
`ValidationError` (reused, no new exception type) on the first
violation. `Component`, `Module`, `ExecutionEngine`, `ExecutionContext`,
`Sequential`, `ports.py`, and `inspection.py` are all unchanged — zero
lines touched; `architecture.py` is a new, standalone module.

Two Staff-review corrections shaped the final contract before any code
was written: "exactly one root" alone is insufficient to prove a tree
(a diamond — `A→B`, `A→C`, `B→D`, `C→D` — has one root and zero
duplicate IDs but a doubly-parented node), and a disconnected cycle is
caught by reachability, not root-counting, since neither cycle node has
zero incoming edges. Both were verified by direct construction before
being frozen into the ADR, and both now have dedicated regression
tests. No separate cycle-detection algorithm was implemented — proven,
not merely assumed, that the existing rules already imply acyclicity
for a valid tree.

An explicit, named limitation carried forward from the audit: the
pre-existing `Module` cycle-registration gap (`a.child = b; b.child = a`
succeeding, then `RecursionError`-ing on traversal) remains unaddressed
— `validate_snapshot()` operates on the snapshot boundary only and
cannot protect against a tree `snapshot()` itself couldn't finish
building. Frozen as an explicit Non-goal (ADR-013), not silently
patched here.

Benchmarked scaling (1/10/100/1,000-node trees) confirms the O(N+E)
design empirically: node count growing 10x costs roughly 8-10x time,
not ~100x — see `evaluation/step9-evaluation.md`.

## Step 10 status

Composition preconditions (A37-A44) are implemented per ADR-014:
`ragtorch.core.ports.check_connection()`, a raising precondition
wrapper — "ask" (`is_compatible()`, `bool`) vs. "enforce"
(`check_connection()`, `None`/raises `ValidationError`). Its body is
exactly `if not is_compatible(...): raise ...`, so `is_compatible()`
remains the single source of truth for compatibility semantics; no
parallel `issubclass()` logic was written. `Component`, `Module`,
`Sequential`, `ExecutionEngine`, `ExecutionContext`,
`ArchitectureSnapshot`, and `validate_snapshot()` are all unchanged —
zero lines touched; `check_connection()` was added to the existing
`ports.py` alongside `is_compatible()`, not a new module.

This step deliberately does **not** integrate `check_connection()`
with `ArchitectureSnapshot`/`validate_snapshot()`, and does not
introduce a `Block`/composite type or graph executor — it proves the
port-level precondition primitive in isolation, per the project's
consistent "one primitive per step" discipline (Steps 6-9). An
explicit regression pair proves `is_compatible()`'s pre-existing
`bool` contract is unaffected by the addition, not merely assumed
from "we didn't edit that function."

Benchmarked overhead (`benchmarks/step10_composition_preconditions.py`):
`check_connection(valid)` is indistinguishable from
`is_compatible(valid)` (~0.1µs both); `check_connection(invalid)`
costs ~0.7µs more, consistent with the added f-string construction and
exception raise on the failure path — see
`evaluation/step10-evaluation.md`.

## Step 11 status

Connection identity and directionality (A45-A51) is implemented per
ADR-015: `ragtorch.core.connection.Connection`, a frozen value type
persisting a single, directed, validated data-flow edge
(`source_node_id`, `source_port: OutputPort`) → (`target_node_id`,
`target_port: InputPort`). `__post_init__` enforces four invariants —
non-empty node IDs, correct port role for each end — before delegating
compatibility to the unchanged `check_connection()` (Step 10).
`Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `validate_snapshot()`, and
`ports.py` itself are all unchanged — zero lines touched;
`connection.py` is a new, standalone module.

A Staff-review correction shaped the final contract before any code
was written: the first draft relied on field type annotations
(`source_port: OutputPort`, `target_port: InputPort`) alone to
guarantee directionality, which is not a runtime guarantee in Python —
and `check_connection()` (ADR-014) explicitly does not normalize
non-`Port` arguments into `ValidationError`, so an annotation-only
`Connection` could have silently constructed with its ends swapped.
Two explicit `isinstance` checks were added at the `Connection`
boundary specifically to close this, without reopening ADR-014's own
documented non-guarantee for `check_connection()` itself.

Fan-out/fan-in cardinality is deliberately left unconstrained (proven
by dedicated tests, not merely unaddressed) — whether either pattern
should be permitted, and where that rule would live, is explicit
future work for a collection/`Block` type built on top of `Connection`,
not decided here. No graph type, no cycles, no execution order, no
serialization: this step proves the element, not the aggregate.

Benchmarked overhead
(`benchmarks/step11_connections.py`): `Connection(valid)` costs ~1.9µs
more than `check_connection()` alone at p50 — the frozen-dataclass
construction path is not free, even though each individual check is
cheap — reported as measured rather than left at an earlier,
incorrect "should be small" prediction. See
`evaluation/step11-evaluation.md`.

## Step 12 status

Composition graph validation (A52-A64) is implemented per ADR-016:
`ragtorch.core.composition.CompositionGraph`/`GraphNode`, an immutable,
validated collection of nodes and `Connection`s enforcing nine
canonical invariants in fixed order — unique node ids, referential
integrity, inherited directionality/compatibility from `Connection`,
no duplicate connections, fan-in ≤ 1 per input port (fan-out
unrestricted), acyclicity, and no dangling connections after node
removal. `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `validate_snapshot()`,
`ports.py`, and `connection.py` are all unchanged — zero lines
touched; `composition.py` is a new, standalone module.

Two Staff-review corrections shaped the final contract. First:
`GraphNode.id` is explicitly graph-local identity, deliberately not
derived from or coupled to `ArchitectureNode.id` (ADR-012's dotted
`named_modules()` path) — an unrelated `Module`-tree refactor (an
attribute rename, a tree restructuring) must never silently break
composition-graph identity, which matters for future caching,
serialization, diffing, and reproducibility use cases. Second: cycle
detection is scoped as a property of *this* graph type describing
ordinary data-flow composition, not a universal invariant for every
future RAG-MODULE graph concept — a future `Loop`/`Retry` primitive is
explicit higher-level control-flow work, not an exception carved into
`CompositionGraph` itself.

A real bug was caught by this step's own benchmark, not by unit tests:
the first `_has_cycle()` implementation used recursive DFS, which
raised `RecursionError` on a 1,000-node linear chain (every unit test
used ≤4 nodes and never exercised this path). Fixed by rewriting it as
an iterative Kahn's-algorithm topological sort before commit — concrete
evidence for why this project benchmarks at multiple scales rather
than trusting correctness proven only at a single small size.

Functional updates (`add_node`/`add_connection`/`remove_node`/
`remove_connection`) each return a new, independently-validated graph
rather than mutating `self`, consistent with every prior structural
type's immutability guarantee — but each update re-validates the
entire resulting graph rather than incrementally checking only the
delta, an explicit, measured, and accepted tradeoff (see
`evaluation/step12-evaluation.md` Limitations), not a silently-absorbed
cost.

Benchmarked scaling (10/100/1,000-node linear chains) confirms the
O(N+E) design empirically: node count growing 10x costs roughly 10-12x
time, not ~100x — see `evaluation/step12-evaluation.md`.

## Step 13 status

Execution planning (A65) is implemented per ADR-017:
`ragtorch.core.execution_plan.plan()`, deriving a deterministic
`ExecutionPlan` (ordered `ExecutionStep`s, each carrying `node_id` and
direct `dependencies`) from a valid `CompositionGraph` via Kahn's
algorithm with an explicit FIFO `collections.deque` ready queue.
`Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `CompositionGraph`
(including `_has_cycle()`, whose LIFO shape was deliberately left
unchanged), and `Connection` are all unchanged — zero lines touched;
`execution_plan.py` is a new, standalone module.

This step is the first in the project to go through **two rounds of
adversarial architectural review before any implementation existed**.
13B.3 found one BLOCKER (ADV-01): the ADR's first draft claimed
`plan()` reuses `CompositionGraph._has_cycle()`'s exact traversal
shape for its declared-order tie-break, which direct construction
proved false — `_has_cycle()`'s queue is LIFO, and would have silently
reversed ties relative to the declared order the ADR promised. 13B.5,
re-attacking the corrected FIFO design rather than assuming the fix
was sufficient, found a second, more subtle issue (ADV-04, MINOR):
"tie-broken by graph.nodes order" is precise only for nodes ready at
the very start of planning — nodes that become ready mid-traversal are
ordered by `graph.connections` discovery order instead, a genuinely
different (though equally deterministic) rule. Both findings are
reflected as named regression tests, not just prose, so a future
refactor cannot silently reintroduce either defect.

`plan()` does not re-validate graph structure, never executes a
component, never mutates or retains a reference to its source graph,
and contains no runtime objects — proven by dedicated tests
(`ExplodingComponent`, `dataclasses.fields()` introspection,
before/after snapshot comparison), not merely asserted from the ADR's
design intent.

Benchmarked scaling (10/100/1,000/10,000-node linear chains and wide
fan-out, plus two diamond-heavy shapes) confirms roughly linear growth
through 1,000 nodes with a modest superlinear tail at 10,000 —
reported as measured, not smoothed over — see
`evaluation/step13-evaluation.md`. No `RecursionError` or other
scale-dependent failure occurred at any tested size, since `plan()`
used an iterative `deque`-based algorithm from its first
implementation, unlike Step 12's `_has_cycle()`, which required a
post-hoc fix after failing at 1,000 nodes.

## Next priority

1. Add concurrency tests around event identity before moving event delivery to execution-scoped ownership.
2. Design a `Block` type that consumes `CompositionGraph` (Step 12) as its validated structural foundation — the payoff every primitive since Step 6 exists to enable.
3. Design an executor that consumes `ExecutionPlan` (Step 13) — synchronous first, with the data model already proven not to foreclose async/parallel execution later.
4. Consider whether the pre-existing `Module` cycle-registration gap (A29's named limitation) is worth a dedicated future ADR.
5. Consider whether `CompositionGraph`'s full-revalidation-per-update cost (A61's named limitation) is worth an incremental-validation optimization, once a real workload demonstrates it matters.
6. Keep the milestone rule: design → ADR → contract → implementation → tests → benchmark → evaluation → CI → documentation.

The Component migration is intentionally **not** a rename of `Module`. We
first proved the contract and compatibility boundary (Step 6) before any
future migration decision is made. Ports (Step 7) are additive,
optional metadata layered beside Component, not a growth of its core
contract. The architecture snapshot (Step 8) gives Ports and any future
Block/graph layer a canonical structural representation to build on,
without prematurely committing to data-flow or serialization semantics.
Architecture validation (Step 9) gives that representation a fail-fast
correctness check, independent of execution, before any future
composition layer needs to reason about it.
