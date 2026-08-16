# ADR-015: Connection Identity and Directionality

## Status

Accepted

Confirmed by real GitHub Actions CI on PR #6 (run
[31940799953](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31940799953)):
258/258 tests passed on Python 3.10, 3.11, and 3.12; lint green on all
three. Not accepted from local checks alone, per project convention.

## Context

After Step 10, five independent primitives exist:

- `Component` (ADR-010): `name`, `component_type`, `__call__`.
- `InputPort`/`OutputPort`/`is_compatible()` (ADR-011): a component's
  declared input/output boundary, and a pairwise, in-the-moment
  compatibility check — `issubclass(output.type, input.type)`,
  `True`/`False`.
- `ArchitectureSnapshot`/`ArchitectureNode`/`ArchitectureChild`
  (ADR-012): a `Module` tree's *containment* structure only.
  `ArchitectureChild` is explicitly named to avoid implying data-flow —
  it represents `parent.child_attr = child`, never "this component's
  output feeds that component's input." `ArchitectureNode.input_ports`/
  `output_ports` exist as fields but are always empty in practice: no
  code path populates them.
- `validate_snapshot()` (ADR-013): validates the containment tree is a
  well-formed rooted tree. Says nothing about ports.
- `check_connection()` (ADR-014): raises if a proposed
  output-to-input pairing is incompatible, returns `None` otherwise.
  It checks a connection would be legal; it does not represent one.

**No data structure anywhere in this codebase persists the fact "this
output feeds that input."** `check_connection()` answers the question
in the moment and forgets the answer immediately. This is the concrete
gap behind `docs/architecture/requirements-matrix-v0.1.md`'s R7
("Composability... No general Block/Graph model") and A2 ("Block
abstraction not yet formalized"), and behind `v0.1-architecture.md`
§4's unimplemented composition primitives.

Before any `Block`/graph/composition layer can exist, something has to
answer a narrower question first: **what does one connection *look
like* as data** — its identity, its directionality — independent of
how many connections might later form a graph, whether that graph
allows cycles, how it executes, or how it serializes. Those are Block-
or graph-layer questions; this ADR does not answer them (see
Non-goals). Confirmed with the project owner before drafting: the
narrower "prove one connection" scope was chosen deliberately over
answering the full graph-design question list in one step, continuing
the project's established one-primitive-per-step discipline (Steps
6-10 each did exactly this).

## Problem

We need a value type representing a single, directed, validated
connection from one component's declared output port to another's
declared input port — persisted as data, not just checked in passing —
so that a future graph/`Block` layer has something concrete to hold a
collection of, rather than needing to invent connection identity from
scratch alongside the graph itself.

## Decision

### Public contract

```python
@dataclass(frozen=True)
class Connection:
    """A single, directed, validated data-flow edge.

    Construction-time validated: node identifiers must be non-empty
    strings, source_port must actually be an OutputPort, target_port
    must actually be an InputPort, and the pair must be compatible per
    check_connection() (ADR-014). Any violation raises ValidationError
    and no Connection is created. A successfully constructed Connection
    is therefore always known-valid for its lifetime — there is no
    invalid Connection instance to guard against later.
    """

    source_node_id: str
    source_port: OutputPort
    target_node_id: str
    target_port: InputPort

    def __post_init__(self) -> None:
        if not isinstance(self.source_node_id, str) or not self.source_node_id:
            raise ValidationError("Connection source_node_id must be a non-empty string.")
        if not isinstance(self.target_node_id, str) or not self.target_node_id:
            raise ValidationError("Connection target_node_id must be a non-empty string.")
        if not isinstance(self.source_port, OutputPort):
            raise ValidationError("Connection source_port must be an OutputPort.")
        if not isinstance(self.target_port, InputPort):
            raise ValidationError("Connection target_port must be an InputPort.")
        check_connection(self.source_port, self.target_port)
```

- `source_node_id`/`target_node_id` reuse `ArchitectureNode.id`'s
  existing dotted-path scheme (ADR-012) — not a new identity system.
  A `Connection` names *which nodes* it connects, using identifiers
  that already mean something elsewhere in this codebase.
- `source_port`/`target_port` are the actual `OutputPort`/`InputPort`
  instances, not just names/types — so a `Connection` is self-describing
  without requiring a caller to re-look-up port metadata from a node id.
- **Directionality is a runtime-checked invariant, not merely a type
  annotation.** Python does not enforce dataclass field annotations at
  runtime, and `check_connection()` (ADR-014) explicitly assumes it
  receives real `OutputPort`/`InputPort` instances without normalizing
  misuse into `ValidationError` — so if `Connection` relied on
  annotations alone, `Connection(source_port=InputPort(...), ...)`
  would construct successfully (or fail with an unrelated
  `AttributeError` deep inside `check_connection()`), silently
  producing a "connection" that reads backwards. `__post_init__`
  therefore checks `isinstance(self.source_port, OutputPort)` and
  `isinstance(self.target_port, InputPort)` explicitly, before
  delegating compatibility to `check_connection()`. This is the one
  runtime type-identity check this ADR adds beyond ADR-014's existing
  contract, and it is scoped narrowly: it establishes *which port
  plays which role*, not general defensive argument validation
  elsewhere in the codebase.
- Node identifier validation (non-empty string) exists so a
  `Connection` cannot silently reference "no node in particular" —
  `""` is exactly the kind of value that would otherwise pass through
  unnoticed and only fail confusingly at a later lookup.
- Validation happens in `__post_init__`, calling `check_connection()`
  exactly once, unchanged (ADR-014's single source of truth for
  compatibility semantics is inherited, not re-implemented).

### Identity: value equality, not object identity

`Connection` is a plain frozen `@dataclass`, so two `Connection`
instances with the same four field values are equal
(`dataclass(frozen=True)` generates `__eq__` from fields by default) —
consistent with `ArchitectureChild`'s existing value-equality identity
in the same module family. `Connection` does not carry a UUID, a
sequence number, or any identity beyond "which output port on which
node feeds which input port on which node." Two logically identical
connections constructed independently compare equal; this is
deliberate, not an oversight — see the Alternatives section for why a
synthetic identity was rejected for this step.

### Location: new module, `src/ragtorch/core/connection.py`

Unlike `check_connection()` (Step 10, added to the existing
`ports.py` because it was a thin wrapper over `is_compatible()`),
`Connection` is a genuinely new concern: a persisted fact about two
nodes' relationship, not a boundary-metadata check. It depends on both
`ports.py` (`OutputPort`/`InputPort`/`check_connection`) and node
identifiers in `ArchitectureNode`'s scheme (ADR-012), so it does not
belong inside either existing module — matching the precedent set by
Steps 8/9 (`inspection.py`, `architecture.py`) of introducing a new
module per new concern.

## Non-goals

Explicitly deferred, not part of this decision:

- **Fan-out/fan-in cardinality rules.** Whether one output can
  legally feed multiple inputs, or one input can legally receive
  multiple outputs, is a real question this ADR does not answer.
  `Connection` itself places no such constraint — nothing here
  prevents constructing two `Connection` instances that share a
  `source_node_id`/`source_port`, or two that share a
  `target_node_id`/`target_port`. Enforcing (or deliberately
  permitting) either pattern is future work, once a collection type
  exists to enforce it against.
- **A `ConnectionGraph`/`Block` aggregate type.** No collection type
  holding multiple `Connection`s is introduced. This ADR proves the
  element; a future ADR designs the collection.
- **Cycles.** Not addressed, structurally or for execution — there is
  no graph yet for a cycle to exist in.
- **Execution order derivation.** Nothing here determines what runs
  before what.
- **Serialization.** No JSON/other format for `Connection` is defined.
- **Observability/evaluation attachment to edges.** Tracing or
  metrics per-connection is not designed here.
- **Async execution implications.** Not addressed.
- **Integration with `ArchitectureSnapshot`/`validate_snapshot()`.**
  `Connection` does not read or produce an `ArchitectureSnapshot`.
  `ArchitectureChild` (containment) and `Connection` (data-flow) remain
  two independent concepts, per ADR-012's own explicit non-goal that
  containment must never imply data-flow. Wiring them together (e.g.
  "does every `Connection` reference two nodes that actually exist in
  a given snapshot") is deferred until a real consumer needs that
  cross-check.
- **A `Block` class itself.** `v0.1-architecture.md`'s "Block" remains
  a named future concept, not implemented here.

## Alternatives considered

- **Rely on type annotations alone for directionality, with no runtime
  `isinstance` check.** Rejected after review: Python does not enforce
  dataclass field annotations at runtime, and `check_connection()`
  (ADR-014) explicitly does not normalize non-`Port` arguments into
  `ValidationError` — so `Connection(source_port=InputPort(...), ...)`
  would either construct successfully or fail with an unrelated,
  confusing `AttributeError`, silently permitting a backwards
  "connection." A narrow, explicit `isinstance` check at the
  `Connection` boundary closes this without reopening ADR-014's own
  documented non-guarantee for `check_connection()` itself — the check
  lives in the new code that needs it, not retrofitted onto the
  existing function.
- **Give `Connection` a synthetic identity (UUID or sequence number).**
  Rejected for this step: nothing yet needs to distinguish two
  structurally-identical connections as different *instances* (e.g. no
  registry, no mutation-over-time, no "replace this specific
  connection" operation exists). Value equality is simpler and
  matches `ArchitectureChild`'s precedent. If a real need for identity
  beyond value equality is demonstrated later (e.g. a mutable
  connection registry), it is a deliberate, additive change — not
  assumed now.
- **Store ports by name/type only, not by instance.** Rejected:
  `ArchitectureNode` already carries typed port instances (once
  populated — see ADR-012's deferred port-population mechanism), and
  requiring a `Connection` consumer to re-resolve `(node_id, port_name)`
  back into an `OutputPort`/`InputPort` before it could re-check
  compatibility would be strictly less useful than holding the port
  objects directly, for no space savings that matters at this scale.
- **Represent a connection as a plain tuple instead of a dataclass.**
  Rejected: every other structural type in this codebase
  (`InputPort`, `OutputPort`, `ArchitectureNode`, `ArchitectureChild`)
  is a named, frozen dataclass, not a tuple — consistency with the
  established style outweighs the marginal verbosity, and named fields
  make `source_node_id` vs. `target_node_id` unambiguous at every call
  site in a way `tuple[str, OutputPort, str, InputPort]` would not be.
- **Design the full graph model now, since the requirements matrix
  already names it as the destination.** Rejected for this step, for
  the same reason Step 10 rejected building `Block` early: no
  collection of connections exists yet to validate the right aggregate
  API shape against. Proving `Connection` first, then letting a graph
  type consume it once justified, follows the same "prove the
  primitive before the composite" sequencing used for every prior step
  (`Component` → `Sequential`, `Port` → `Snapshot` → `Validation` →
  `check_connection` individually before anything connects them).

## Security

`Connection.__post_init__` calls only the existing `check_connection()`
(ADR-014), which itself calls only `is_compatible()` (ADR-011) — no new
reflection, no execution, no arbitrary object inspection. `Connection`
reads only `source_port`/`target_port`'s already-validated `type`/`name`
fields (validated at `Port` construction, ADR-011) and the caller-supplied
`source_node_id`/`target_node_id` strings, which it does not interpret,
resolve, or look up against any snapshot.

## Dependency review

Zero new runtime dependencies. `connection.py` imports
`ragtorch.core.ports` (`OutputPort`, `InputPort`, `check_connection`)
and the standard library `dataclasses` — no other internal module
dependency, no provider dependency.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `ArchitectureChild`,
`validate_snapshot()`, `is_compatible()`, or `check_connection()`
themselves. `Connection` is a pure addition, in a new module.

## Testing strategy

- Constructing a `Connection` from a compatible output/input pair
  succeeds (exact-type and subtype cases, mirroring `is_compatible()`'s
  own coverage).
- Constructing a `Connection` from an incompatible pair raises
  `ValidationError` (via `check_connection()`, not re-implemented
  compatibility logic).
- **Directionality is runtime-enforced, not merely annotated**:
  passing an `InputPort` as `source_port` raises `ValidationError`
  naming `source_port`; passing an `OutputPort` as `target_port`
  raises `ValidationError` naming `target_port`. These are the tests
  that would have caught the flaw in this ADR's own first draft, which
  relied on type annotations alone.
- Empty-string `source_node_id`/`target_node_id` each raise
  `ValidationError` independently (two separate tests).
- `Connection` is immutable (frozen dataclass — attribute assignment
  raises).
- Two `Connection`s with identical field values are equal (`==`);
  two differing in any one field (e.g. `target_node_id`) are not.
- `Connection` is hashable, and equal instances hash equally — the
  frozen-dataclass default, confirmed by a dedicated test (not
  assumed), since a future graph/`Block` layer holding connections in
  a `set`/as `dict` keys depends on this.
- No re-implementation of compatibility logic: a test verifying that a
  `Connection` construction failure and a direct `check_connection()`
  failure for the same port pair raise `ValidationError` with the same
  message, proving `Connection` delegates rather than duplicates.
- Fan-out/fan-in is explicitly *not* constrained: a test constructing
  two valid `Connection`s that share a `source_node_id`/`source_port`
  (or share a `target_node_id`/`target_port`) both succeed — proving
  Step 11 does not accidentally invent a cardinality rule nobody
  decided on, not proving fan-out is "supported" by any future graph
  layer.
- Integration: a realistic Retriever→Reranker→Generator chain
  (mirroring Step 7/10's fixtures) — compatible `Connection`s
  construct successfully; the deliberately incompatible
  Retriever→Generator pair raises.
- Security/provider-independence: no provider import in
  `connection.py` (AST-based check, reusing the established pattern).

## Benchmark strategy

Per ADR-009, `benchmarks/step11_connections.py`. Measures `Connection`
construction for a compatible pair (expected: roughly
`check_connection(valid)`'s Step 10 baseline, ~0.1µs, plus dataclass
allocation) and an incompatible pair (expected: roughly
`check_connection(invalid)`'s Step 10 baseline, ~0.8µs, since
construction fails before the dataclass is fully initialized). No hard
threshold asserted, consistent with prior benchmarks' methodology.

## Consequences

- A future graph/`Block` layer has a ready-made, already-tested
  connection element to hold a collection of, rather than needing to
  invent connection identity and directionality alongside the
  aggregate type itself.
- The containment/data-flow separation established in ADR-012
  (`ArchitectureChild` vs. an eventual data-flow concept) is now
  concretely realized: `ArchitectureChild` for containment,
  `Connection` for data-flow, both independent, neither assuming the
  other.
- Scope stays deliberately narrow: no graph, no cardinality rules, no
  cycles, no execution — consistent with every prior step's discipline
  of proving one primitive before building on it. The fan-out/fan-in
  question is now sharply scoped for a future step, rather than
  answered ad hoc inside this one.
