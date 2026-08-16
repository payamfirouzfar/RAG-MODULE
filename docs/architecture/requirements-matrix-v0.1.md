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

## Next priority

1. Add concurrency tests around event identity before moving event delivery to execution-scoped ownership.
2. Design a `Block`/graph composition layer that uses `is_compatible()` (Ports), `ArchitectureSnapshot` (Step 8), and `validate_snapshot()` (Step 9) together to validate an actual architecture before execution — the payoff all three exist to enable.
3. Consider whether the pre-existing `Module` cycle-registration gap (A29's named limitation) is worth a dedicated future ADR.
4. Keep the milestone rule: design → ADR → contract → implementation → tests → benchmark → evaluation → CI → documentation.

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
