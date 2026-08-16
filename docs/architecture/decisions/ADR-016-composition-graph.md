# ADR-016: Composition Graph

## Status

Proposed

## Context

After Step 11, six independent primitives exist:

- `Component` (ADR-010): `name`, `component_type`, `__call__`. No
  ports, no membership, no graph awareness.
- `InputPort`/`OutputPort`/`is_compatible()` (ADR-011): a component's
  declared boundary and a pairwise compatibility check.
- `ArchitectureSnapshot`/`ArchitectureNode`/`ArchitectureChild`
  (ADR-012): a `Module` tree's *containment* structure only, never
  data-flow.
- `validate_snapshot()` (ADR-013): validates that containment tree is
  a well-formed rooted tree.
- `check_connection()` (ADR-014): raises if a proposed output-to-input
  pairing would be illegal; checks in the moment, persists nothing.
- `Connection` (ADR-015): persists one such pairing as data —
  `(source_node_id, source_port) -> (target_node_id, target_port)` —
  but a single `Connection` cannot represent a composition. Nothing
  yet holds a *collection* of connections, or the nodes they relate.

`docs/architecture/requirements-matrix-v0.1.md` still lists `R7`
("Composability... No general Block/Graph model") and `A2` ("Block
abstraction not yet formalized") as open. `v0.1-architecture.md` §2/§4
name the destination — `Components → Blocks → Graph/Architecture` —
without specifying what the graph itself looks like as data, or what
invariants it enforces before any `Block`/execution layer touches it.

**This ADR does not build `Block`, an execution planner, or an
execution engine.** It answers the next narrower question: given a set
of nodes (each wrapping a `Component`) and a set of `Connection`s
between them, what makes that collection a *valid* composition — as a
static, structural fact, independent of how or whether it ever
executes? Confirmed with the project owner before drafting: this
continues the established one-primitive-per-step discipline (Steps
6-11), this time proving the *aggregate* now that the *element*
(`Connection`, Step 11) already exists and is accepted.

```text
Component (ADR-010)
      |
      v
InputPort / OutputPort / is_compatible() (ADR-011)
      |
      v
check_connection() (ADR-014)
      |
      v
Connection (ADR-015)
      |
      v
CompositionGraph (this ADR)
      |
      v
Future Block / execution planner / execution engine
```

## Problem

We need a value type representing a *validated collection* of nodes
and directed connections between them — with referential integrity
(every connection's endpoints reference nodes that actually exist in
the graph), no duplicate edges, an explicit and deliberately
conservative cardinality rule, and no cycles — so that a future
`Block`/execution layer has a trustworthy structural foundation to
build on, rather than needing to invent graph-level validation from
scratch alongside execution semantics.

## Decision

### Naming: `CompositionGraph`, not `Graph`

`Graph` alone invites future collision with unrelated graph concepts
this project may eventually need (a knowledge graph, a retrieval
graph, an execution graph). `CompositionGraph` names exactly what this
type is a graph *of*: component composition, not any other kind of
graph. This mirrors the same naming discipline that chose
`ArchitectureChild` over the more generic (and misleading) "Edge" in
ADR-012.

### Module: `src/ragtorch/core/composition.py`

A new module, not an addition to `connection.py` or `architecture.py`:
this is a genuinely new concern (validated aggregate structure), not a
thin wrapper over an existing function (contrast Step 10's
`check_connection()`, correctly added to `ports.py`). Matches the
precedent of Steps 8/9/11 each introducing a new module for a new
concern.

### Public contract

```python
@dataclass(frozen=True)
class GraphNode:
    """One component's identity and membership within a CompositionGraph.

    Deliberately minimal: id and component only. Ports remain external
    metadata per ADR-011 Non-goals — GraphNode does not gain
    input_ports/output_ports fields just because the graph needs port
    information; that information already lives on the OutputPort/
    InputPort instances a Connection references directly.
    """

    id: str
    component: Component

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValidationError("GraphNode id must be a non-empty string.")
```

**`GraphNode.id` is graph-local identity, not an architecture path.**
It is not derived from, coupled to, or required to match
`ArchitectureNode.id` (ADR-012's dotted `named_modules()` path), even
though a caller is free to reuse the same string for both today if
convenient. The two identity systems are deliberately independent: an
`ArchitectureNode.id` describes *where* a component sits in a `Module`
containment tree, and can change under an ordinary refactor (an
attribute rename, a tree restructuring) that has nothing to do with
the *composition* that node participates in. A `CompositionGraph`
built for caching, serialization, diffing, or reproducibility needs
node identity that survives exactly that kind of unrelated
architecture reshuffling — coupling `GraphNode.id` to
`ArchitectureNode.id` would silently break every one of those future
use cases the moment someone renamed an attribute. `GraphNode`
therefore accepts any non-empty string a caller supplies; it does not
read, validate against, or import anything from `inspection.py`.

### `CompositionGraph` is data-flow composition, not a universal graph abstraction

`CompositionGraph`'s acyclicity requirement (see below) is a property
of *this* graph type, describing ordinary data-flow composition — not
a claim that every future RAG-MODULE graph concept must be acyclic.
`v0.1-architecture.md` §4 already names `Loop`/`Retry`/`Conditional`/
`Router` as distinct future composition primitives with their own
control-flow semantics; a future `KnowledgeGraph`, `ExecutionGraph`, or
`AgentGraph` (if any of these are ever built) would each define their
own invariants independently. `CompositionGraph` is scoped narrowly to
one thing: is this collection of nodes and directed data-flow
connections a valid, executable-in-principle composition — not a
general-purpose graph library import for the rest of the framework to
reuse indiscriminately.

```python
@dataclass(frozen=True)
class CompositionGraph:
    """An immutable, validated collection of GraphNodes and Connections.

    Construction-time validated: unique non-empty node ids, every
    Connection's source_node_id/target_node_id references a node that
    exists in this graph, no duplicate Connections, at most one
    incoming Connection per (target_node_id, target_port), and no
    cycles. Any violation raises ValidationError and no CompositionGraph
    is created.
    """

    nodes: tuple[GraphNode, ...]
    connections: tuple[Connection, ...]

    def __post_init__(self) -> None: ...  # see Construction invariants

    def add_node(self, node: GraphNode) -> CompositionGraph:
        """Return a new CompositionGraph with node added. Does not mutate self."""

    def add_connection(self, connection: Connection) -> CompositionGraph:
        """Return a new CompositionGraph with connection added. Does not mutate self."""

    def remove_node(self, node_id: str) -> CompositionGraph:
        """Return a new CompositionGraph without the given node.

        Raises ValidationError if any existing Connection still
        references node_id — a node cannot be removed out from under a
        connection that depends on it; the caller must remove the
        connection(s) first. This keeps removal from silently producing
        an invalid intermediate state.
        """

    def remove_connection(self, connection: Connection) -> CompositionGraph:
        """Return a new CompositionGraph without the given connection."""
```

`add_node`/`add_connection`/`remove_node`/`remove_connection` each
construct and return a **new** `CompositionGraph` (which re-runs the
same `__post_init__` validation) rather than mutating `self` — see
"Immutable value, not a mutable builder" below.

### Construction invariants — the canonical list

This is the single canonical statement of what makes a
`CompositionGraph` valid. Every invariant below maps to exactly one
`__post_init__` check and at least one dedicated test — the ADR, the
implementation, and the test suite are required to agree on this list
rather than tests being an independently-invented set of examples.
Checked in `__post_init__` in this fixed order (fail on the first
violation, mirroring `validate_snapshot()`'s established fixed-order
pattern from ADR-013):

1. **Node ids are unique.** No two `GraphNode`s in `nodes` share an
   `id`. (Non-emptiness of a single id is a `GraphNode` invariant,
   checked once at `GraphNode` construction — not re-checked here.)
2. **Every connection references existing nodes.** Every
   `Connection.source_node_id` and `Connection.target_node_id` must
   equal some `GraphNode.id` already present in `nodes` (referential
   integrity).
3. **Every connection is directionally `OutputPort` → `InputPort`.**
   Already guaranteed by `Connection.__post_init__` (ADR-015) for any
   `Connection` instance that exists at all — `CompositionGraph` does
   not re-check this, it inherits the guarantee for free by only ever
   holding real `Connection` instances.
4. **Every connection is port-compatible.** Same as above — inherited
   from `Connection`'s own construction-time `check_connection()` call,
   not re-verified here.
5. **No duplicate connections.** No two entries in `connections` are
   equal (`Connection`'s existing value equality, ADR-015, is reused
   directly — not re-implemented).
6. **Every target port has at most one incoming connection (fan-in
   ≤ 1).** At most one `Connection` may target a given
   `(target_node_id, target_port)` pair. See "Cardinality" below for
   the reasoning.
7. **A node may have unlimited outgoing connections (fan-out
   unrestricted).** No invariant to check — the absence of a fan-out
   limit is itself the design choice; recorded here so the canonical
   list is complete, not because there is code enforcing it.
8. **The graph is acyclic.** No directed cycle exists among
   `connections`. Detected via a standard DFS/Kahn-style traversal over
   `(source_node_id, target_node_id)` pairs — no new dependency, no
   `networkx`.
9. **Removing a node cannot silently leave dangling connections.**
   Enforced by `remove_node()` raising if any existing `Connection`
   still references the node being removed — not a `__post_init__`
   check (nothing to remove at construction time), but a construction
   invariant preserved across every graph-producing operation.

Invariants 3 and 4 are listed for completeness — they are structural
facts about `CompositionGraph` that a reader needs to know hold, even
though the enforcing code lives in `Connection`, not here. This is
deliberate: `CompositionGraph` does not duplicate `Connection`'s
validation, the same "single source of truth" discipline ADR-014
established for `check_connection()`/`is_compatible()` and ADR-015
continued for `Connection`/`check_connection()`.

### Determinism

`nodes` and `connections` are ordered immutable tuples, not sets or
mapping views — iterating a `CompositionGraph`'s nodes or connections
twice, or iterating two independently-constructed but equal graphs,
yields the same order. This is required, not incidental: a future
execution planner, serializer, cache-key computation, or benchmark
that consumes a `CompositionGraph` must be able to rely on stable
iteration order, or every one of those consumers would need to
re-establish its own ordering independently. `add_node`/
`add_connection` append to the end of the existing tuple (construction
order is preserved); `remove_node`/`remove_connection` filter the
existing tuple (relative order of remaining elements is preserved).

### Cardinality: fan-out unrestricted, fan-in ≤ 1

- **Fan-out (one output feeding multiple inputs) is allowed.** A
  `Retriever`'s output legally feeding both a `Reranker` and an
  `Evaluator` is a normal, useful composition shape; nothing about
  "one producer, many consumers" is semantically ambiguous.
- **Fan-in (multiple outputs feeding the same input) is rejected by
  default.** Two independent `Connection`s both targeting the same
  `(target_node_id, target_port)` raise `ValidationError` at
  `CompositionGraph` construction. This is deliberately conservative:
  an `InputPort` describes one input boundary with one declared type;
  if two producers both feed it, nothing in this codebase says whether
  the consumer receives a list, the last writer wins, both race, or
  this is simply a construction mistake — and answering that question
  is exactly the kind of *component-specific aggregation semantics*
  that belongs to a future explicit fusion/aggregation component (e.g.
  a `Fusion` component exposing two distinct named input ports,
  `inputs_a`/`inputs_b`, so each producer has an unambiguous target),
  not to `CompositionGraph` itself. `CompositionGraph` enforces the
  cardinality rule; it does not decide what fan-in *would* mean if
  permitted.
- This decision is scoped to `CompositionGraph`'s default validation
  only. It is not a claim about `Connection` (ADR-015 explicitly left
  `Connection` itself unconstrained on cardinality — see A50) or about
  any future graph variant that might deliberately choose to allow
  fan-in for a well-defined aggregation semantics.

### Cycles: rejected, but `CompositionGraph` is not the future `Loop` primitive

`v0.1-architecture.md` §4 names `Loop` as a distinct future composition
primitive alongside `Sequential`/`Parallel`/`Conditional`/`Router`.
Rejecting cycles in `CompositionGraph` does not foreclose future
iterative execution — it means an iterative composition, when it
exists, is represented as an explicit higher-level construct (a `Loop`
node/wrapper), not as an accidental cycle silently permitted in the
base graph structure. This mirrors ADR-013's own reasoning for
rejecting cycles in `ArchitectureSnapshot`'s containment tree: cheaper
and safer to reject at the structural layer than to make every future
consumer (execution ordering, in particular) defend against cycles
independently.

### Immutable value, not a mutable builder

`CompositionGraph` follows the same immutable-value pattern as every
prior structural type in this codebase (`InputPort`, `OutputPort`,
`ArchitectureNode`, `ArchitectureChild`, `ArchitectureSnapshot`,
`Connection`) rather than introducing the first mutable container.
`add_node()`/`add_connection()`/`remove_node()`/`remove_connection()`
each return a new, independently-validated `CompositionGraph`; the
receiver is never modified. This is chosen deliberately over an
in-place mutable graph API (`graph.add_node(...)` mutating `graph`)
because:

- it matches every existing primitive's immutability guarantee, so a
  `CompositionGraph` reference can be held, compared, or cached with
  the same confidence as any other value type in this codebase;
- it sidesteps an entire category of future concurrency questions
  (locking, versioning, rollback) that a shared mutable graph would
  otherwise force onto this step, before an execution model exists to
  justify designing them correctly;
- if per-call copying is later shown by real profiling to be a
  bottleneck for very large graphs, an internal builder
  (`CompositionGraphBuilder`) can be introduced as an implementation
  detail without changing this public, value-oriented contract — the
  same escape hatch this ADR keeps open rather than needing now.

### `GraphNode` does not require `Component` conformance checking on construction

`GraphNode.__post_init__` validates only `id` (non-empty string). It
does **not** call `isinstance(component, Component)`. ADR-010
established that `Component` conformance checks are real, measured
cost and must never appear on a hot path, and construction-time
checking every `GraphNode` would put such a check on the path of
building any composition, however large. `GraphNode.component` is
therefore accepted structurally-typed and unchecked at this layer —
consistent with `ArchitectureSnapshot`'s own precedent of never
requiring `isinstance(..., Component)` to build a structural
representation. If a future step demonstrates a real need for
conformance checking, it is an explicit, separate, documented boundary
check (e.g. in a future validation pass equivalent to
`validate_snapshot()`), not folded into `GraphNode` construction.

### `CompositionGraph` never executes a component

Construction, `add_node`, `add_connection`, `remove_node`,
`remove_connection`, and every validation pass read only `GraphNode.id`
and `Connection`'s existing fields. None of them call
`component.__call__` or any descendant of it. This is the same
security posture `ArchitectureSnapshot.snapshot()` established in
ADR-012, extended to a type that, unlike `ArchitectureSnapshot`, holds
actual `Component` instances rather than just descriptive strings.

## Non-goals

Explicitly deferred, not part of this decision:

- **A `Block` type.** `CompositionGraph` is data; `Block` (a reusable,
  itself-composable unit built from a graph) remains unimplemented.
- **Execution planning or execution.** No topological ordering is
  exposed publicly, no scheduling, no `ExecutionEngine` integration.
  Cycle detection's internal traversal is used only to reject cycles;
  it does not produce a public execution order.
- **Async/parallel execution implications.** Not addressed.
- **Serialization.** No JSON/other format for `CompositionGraph` is
  defined.
- **Observability/evaluation attachment to nodes or edges.** Not
  designed here.
- **Integration with `ArchitectureSnapshot`/`validate_snapshot()`.**
  `CompositionGraph` does not read or produce an `ArchitectureSnapshot`.
  Containment (`ArchitectureChild`) and data-flow composition
  (`CompositionGraph`/`Connection`) remain independent concepts, per
  ADR-012's explicit non-goal that containment must never imply
  data-flow.
- **A fan-in override or explicit aggregation primitive.** The default
  fan-in ≤ 1 rule is not configurable in this version; a future
  explicit multi-input aggregation mechanism (if ever justified by a
  real component) is a deliberate, separate, additive decision.
- **`Component` conformance validation as part of `GraphNode`.** See
  above — deferred until a real, demonstrated need exists.
- **Graph mutation beyond the four documented operations.** No
  in-place mutation API, no bulk-replace, no merge-two-graphs
  operation.

## Alternatives considered

- **Call the type `Graph`.** Rejected: too generic for a framework
  that may eventually need several distinct graph concepts (knowledge,
  retrieval, execution, evaluation). `CompositionGraph` names the
  specific responsibility, avoiding a naming collision or an awkward
  future rename.
- **Make `CompositionGraph` a mutable container with in-place
  `add_node`/`add_connection`.** Rejected: breaks the immutable-value
  precedent set by every prior structural type in this codebase and
  reopens concurrency questions (locking, versioning) this step has no
  reason to answer yet. See "Immutable value, not a mutable builder."
- **Permit fan-in by default, with "last connection wins" or
  "aggregate into a list" semantics.** Rejected: inventing an implicit
  aggregation behavior at the graph layer hides a decision that
  belongs to a specific component's semantics, and no real component
  exists yet to prove which behavior (if any) would actually be
  wanted — matching this project's repeated "don't design for
  hypothetical requirements" discipline.
- **Allow cycles and defer acyclicity to a future execution-planning
  step.** Rejected: cheaper to reject a cycle once, at construction,
  than to require every future consumer of `CompositionGraph`
  (execution ordering chief among them) to independently defend
  against one. Matches ADR-013's identical reasoning for
  `ArchitectureSnapshot`.
- **Require `isinstance(component, Component)` at `GraphNode`
  construction.** Rejected per ADR-010's explicit prohibition on
  `Component` conformance checks appearing on paths that run once per
  node in a potentially large composition, without first measuring
  whether it is actually needed.
- **Use `networkx` or another graph library for cycle detection.**
  Rejected: zero new dependencies is an established, hard constraint
  (R1/R11); a DFS/Kahn-style traversal over at most a few hundred
  nodes for any realistic RAG composition needs no library.

## Security

`composition.py` reads only `GraphNode.id`, `GraphNode.component`
(never called), and `Connection`'s already-validated fields. No
`component.__call__` is ever invoked by any `CompositionGraph`
operation — verified by a dedicated test using a component whose
`__call__` raises `AssertionError` if invoked, proving construction
and every graph operation succeed without triggering it. No
reflection, no `vars()`/`__dict__` inspection, no network, no
filesystem.

## Dependency review

Zero new runtime dependencies. `composition.py` imports
`ragtorch.core.component` (`Component`), `ragtorch.core.connection`
(`Connection`), `ragtorch.core.errors` (`ValidationError`), and the
standard library `dataclasses` — no `networkx`, no other graph
library.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `ArchitectureChild`,
`validate_snapshot()`, `InputPort`, `OutputPort`, `is_compatible()`,
`check_connection()`, or `Connection` themselves. `CompositionGraph`
and `GraphNode` are a pure addition, in a new module.

## Testing strategy

Organized around the nine canonical invariants above, not as an
independent collection of examples:

- **Invariant 1 (unique node ids)**: construction with duplicate node
  ids rejected; `GraphNode` empty id rejected independently at
  `GraphNode` construction.
- **Invariant 2 (referential integrity)**: a `Connection` referencing
  an unknown `source_node_id`/`target_node_id` (two separate tests)
  rejected.
- **Invariants 3-4 (directionality, compatibility — inherited from
  `Connection`)**: no dedicated `CompositionGraph`-level test beyond
  what ADR-015 already covers for `Connection` itself; a single
  integration test confirms an incompatible `Connection` cannot even
  be constructed to attempt adding to a graph, proving the inheritance
  holds in practice, not merely by ADR argument.
- **Invariant 5 (no duplicate connections)**: two equal `Connection`
  instances both present in `connections` rejected.
- **Invariant 6 (fan-in ≤ 1)**: two connections targeting the same
  `(target_node_id, target_port)` rejected; two connections targeting
  *different* target ports on the same target node both accepted
  (proves the rule is port-level, not node-level).
- **Invariant 7 (fan-out unrestricted)**: one node as the source of
  multiple connections to different targets, all accepted.
- **Invariant 8 (acyclic)**: two-node cycle rejected, three-node cycle
  rejected, disconnected cycle attached to an otherwise-valid graph
  rejected (mirroring ADR-013's own disconnected-cycle test case); a
  four-node linear chain (A→B→C→D) accepted, proving the check does
  not over-reject a valid acyclic graph.
- **Invariant 9 (no dangling connections after removal)**:
  `remove_node` raises if any existing connection still references the
  node being removed; succeeds and returns a smaller graph when no
  connection references it.
- `GraphNode`: immutable, value equality; `GraphNode.id` accepted as an
  arbitrary caller-supplied string unrelated to any
  `ArchitectureNode.id` — a dedicated test constructs a `GraphNode`
  whose id does not match any real `Module`/`ArchitectureNode` path at
  all, proving no coupling exists.
- Immutability: `CompositionGraph`/`GraphNode` attribute assignment
  raises.
- Functional update semantics: `add_node`/`add_connection` each return
  a new `CompositionGraph`; the original is provably unchanged
  (identity/equality check on the original after the call, not merely
  "the call didn't raise") — chained across three sequential updates
  (`g0` → `g1` → `g2` → `g3`), each prior graph independently checked
  to still lack what was added after it.
- `remove_connection` returns a graph without that connection.
- Determinism: `nodes`/`connections` iteration order is stable across
  repeated access on the same instance, and two independently
  constructed-but-equal graphs iterate in the same order; `add_node`
  appends (new node is last), `remove_node`/`remove_connection`
  preserve relative order of what remains.
- No component execution: a component whose `__call__` raises if
  invoked still participates in graph construction and every graph
  operation without triggering it.
- Provider-independence: no provider import in `composition.py`
  (AST-based check, reusing the established pattern).
- Integration: a realistic Retriever→Reranker→Generator chain, plus a
  Retriever feeding both a Reranker and an Evaluator (fan-out, valid),
  plus two Retrievers both targeting the same Generator input port
  (fan-in, rejected) alongside two Retrievers targeting *different*
  named input ports on a Fusion-like node (both valid) — proving
  port-level, not node-level, cardinality enforcement.

## Benchmark strategy

Per ADR-009, `benchmarks/step12_composition_graph.py`. Measures
`CompositionGraph` construction at 10/100/1,000 nodes (built with a
simple chain or fan-out shape, informational scaling evidence only —
no hard threshold), plus `add_node`/`add_connection` single-operation
cost, plus the two failure paths (duplicate-connection, cycle) to show
how quickly each is rejected. Consistent with prior benchmarks'
methodology: numbers are measured and reported as-is, not optimized
toward a target.

## Consequences

- A future `Block`/execution-planning layer has a trustworthy,
  already-validated structural foundation — referential integrity,
  cardinality, and acyclicity all guaranteed by construction — rather
  than needing to invent and test that validation itself.
- The fan-in question Step 11 deliberately deferred now has a default
  answer (reject), sharply scoped: `CompositionGraph` enforces the
  rule, but does not decide what fan-in aggregation *would* mean if a
  future, explicit mechanism chose to permit it.
- Scope stays deliberately narrow: no `Block`, no execution order, no
  serialization, no observability — consistent with every prior step's
  discipline of proving one primitive before building on it.
