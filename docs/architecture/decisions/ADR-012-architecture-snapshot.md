# ADR-012: Architecture Snapshot

## Status

Proposed

## Context

`Module.inspect()` (ADR-001) is the only existing structured view of a
composed architecture. It works by walking `named_children()` directly
and building an indented string in one pass (`_inspect_children()` in
`module.py`). This is the exact shape of problem R8/A9 name: "no
structured architecture snapshot," "architecture inspection has one
source of truth" listed as a gap. If a JSON or Mermaid view were added
today the way `inspect()` is written, each would independently walk
`_modules` and build its own representation — three renderers, three
places a bug or an inconsistency between them could live, with no
shared source of truth. `docs/architecture/v0.1-architecture.md` §10
already commits to the target direction ("Text, JSON, Mermaid, and
other renderers should consume the same snapshot rather than
maintaining separate graph representations") without anything having
implemented it yet.

Separately: `ports.py` (ADR-011) deliberately did not attach ports to
`Component`. Auditing the current codebase found this holds completely
— there is no `component.input_ports` / `output_ports` property or
convention anywhere; the Step 7 tests attach `InputPort`/`OutputPort`
instances as ad hoc class attributes with no framework-level discovery
mechanism. Any snapshot design must not silently assume ports are
discoverable when they currently are not.

## Problem

We need one canonical, immutable representation of a composed `Module`
tree that:

1. Is built once by walking the tree exactly once (not once per
   renderer).
2. Existing behavior (`inspect()`'s current string output, tested via
   substring assertions in `tests/unit/core/test_module.py`) keeps
   working — this is a migration, not a replacement, per R12/A9's
   backward-compatibility framing.
3. Never executes a component, never reads arbitrary instance state
   (`vars()`/`__dict__`), and therefore cannot leak a secret sitting on
   a component instance.
4. Has deterministic node identity — not `id(node)`, which is
   process-local and breaks reproducibility, diffing, and any future
   evaluation-artifact use (ADR-004's `EvaluationResult` already treats
   reproducibility as a first-class concern; a snapshot with
   non-deterministic identity would undermine that for architecture
   comparisons).

## Decision

### Canonical model, in `src/ragtorch/core/inspection.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field

from ragtorch.core.ports import InputPort, OutputPort


@dataclass(frozen=True)
class ArchitectureNode:
    id: str
    name: str
    component_type: str
    input_ports: tuple[InputPort, ...] = field(default_factory=tuple)
    output_ports: tuple[OutputPort, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ArchitectureChild:
    """A parent -> child tree containment relationship.

    Deliberately NOT named ArchitectureEdge: this represents Module
    registration/tree structure only, never a data-flow relationship
    ("this component's output feeds that component's input"). See
    Non-goals — conflating the two under one name would misrepresent
    what Step 8 actually knows.
    """

    parent_id: str
    child_id: str


@dataclass(frozen=True)
class ArchitectureSnapshot:
    nodes: tuple[ArchitectureNode, ...]
    children: tuple[ArchitectureChild, ...]


def snapshot(module: Module) -> ArchitectureSnapshot:
    """Build an immutable snapshot of module's architecture.

    Walks the tree exactly once via Module.named_modules() (already
    deterministic, already tested). Never calls module(...) or any
    descendant; never reads instance __dict__/vars(). See Security.
    """
    ...
```

`Module` gains a thin convenience method delegating to the free
function, so the common case reads naturally without requiring an
import of `inspection`:

```python
class Module:
    def snapshot(self) -> ArchitectureSnapshot:
        return snapshot(self)
```

The actual snapshot-building logic lives in the free function in
`inspection.py`, not duplicated onto `Module` — `Module.snapshot()` is
purely a one-line delegation, kept easy to test/replace independently
of `Module` itself (consistent with keeping `Module`'s own
responsibilities narrow, per ADR-001).

`nodes`/`children` are frozen tuples (not `list`), matching the
project's existing "the snapshot represents a point in time" convention
(`ExecutionContext.metadata` is similarly frozen into an immutable
mapping — see ADR-002) — a snapshot handed to a renderer cannot be
mutated to silently drift from what was actually walked.

### Node identity: dotted path, not `id(node)`

`ArchitectureNode.id` is the dotted path already produced by
`Module.named_modules()` — e.g. `"root.retriever.reranker"` — which is
existing, tested, deterministic code (`tests/unit/core/test_module.py`
already asserts on `named_modules()`'s output shape). This directly
satisfies the determinism requirement without inventing a new identity
scheme: two snapshots of the same architecture, built in the same or a
different process, produce identical node IDs, because the path is a
pure function of the tree structure and registered names, not of
Python object identity.

### `ArchitectureChild`, not `ArchitectureEdge`

Per Staff review during design: naming this `ArchitectureEdge` would
imply general graph/data-flow semantics ("this output feeds that
input") that Step 8 does not have and does not attempt to derive. The
only relationship this ADR's snapshot actually knows is parent-child
tree containment via `Module.register_module()`/`named_children()`.
Using a name that explicitly says "child," not "edge," keeps a future
real data-flow edge type (`ArchitectureEdge` or similar, introduced
once a composition/graph layer — Step 10+ — defines what "A feeds B"
means) unambiguous and non-conflicting.

### Ports: present in the shape, empty by default, never auto-discovered

`ArchitectureNode.input_ports`/`output_ports` default to `()`. Nothing
in `snapshot()` inspects a `Module` for port attributes — there is no
existing convention to discover (see Context) and this ADR does not
invent one. A node's ports are populated only when the (not-yet-
designed) API for explicitly supplying them is used — out of scope for
Step 8's first cut; the field exists in the dataclass shape now so a
future port-aware snapshot call doesn't require reshaping
`ArchitectureNode` itself. This mirrors ADR-011's own precedent:
`Component` was designed so `capabilities`/`configuration` could be
added later without breaking it; here, `ArchitectureNode` is designed
so per-node ports can be populated later without breaking it.

### `inspect()` becomes a renderer over the snapshot, not a competing walk

`Module.inspect()`'s public contract (verified by
`test_inspect_contains_counts_and_tree`: output contains `"Modules: N"`,
`"Depth: N"`, and `"name (Type)"` lines) is preserved exactly — same
strings, same test passes unmodified. Internally, `inspect()` is
rewritten to call `snapshot(self)` and render text from the result,
rather than walking `_modules` a second, independent way. This is the
concrete fix for the "multiple representations that eventually
disagree" risk raised during design review: after this change there is
exactly one tree-walk (`snapshot()`'s), and `inspect()` is a consumer
of it, not a parallel implementation.

### Security: never read arbitrary instance state

`snapshot()` reads only `module.name`, `module.component_type`, and
`module.named_children()` — all three already-public, already-
intentional surface (ADR-010). It never calls `vars(module)`,
`module.__dict__`, or any reflection over instance attributes beyond
those three. This is a stronger guarantee than filtering through
`redact()`/`is_sensitive_key()` (`ragtorch.core.logging`, ADR-003):
those are heuristics for *known* fields being logged deliberately, not
a safe way to walk *unknown* object state — a secret sitting on a
component instance (e.g. `self.api_key`) is structurally unreachable by
`snapshot()`, not merely filtered out after being read.

### No execution

`snapshot()` never calls `module(...)` or any descendant's `__call__`/
`forward`. It only walks `named_children()` — the same guarantee
`Module.inspect()` already provides today, carried forward exactly.

## Non-goals

Explicitly deferred, not part of this decision (confirmed with the
project owner during design review, not assumed):

- **Data-flow edges** ("this component's output feeds that component's
  input"). `Sequential`'s step ordering is a Python `list`, not an
  explicit graph structure — audited directly, confirmed no existing
  code tracks this as a distinct concept from tree position. Deriving
  edges from `Sequential`'s specific internal convention was considered
  and explicitly rejected: it would couple the snapshot model to one
  composite's implementation detail before a general composition/graph
  contract (a future step, per the roadmap) exists to define the
  semantics properly.
- **Automatic port discovery.** No new `Module`/`Component` attribute
  or convention is introduced to make ports discoverable; see Decision.
- **Serialization** (`to_json()`, `to_dict()`). Deferred until a real
  consumer needs it — committing to field names/versioning now would be
  premature per the "contracts before implementation, but only the
  contract actually needed" principle already applied in ADR-010/011.
- **Renderers beyond the `inspect()` migration** (Mermaid, Graphviz,
  a JSON renderer). `v0.1-architecture.md` §10 names these as an
  eventual direction; Step 8 proves the snapshot model exists and has
  exactly one existing consumer (`inspect()`), not that every renderer
  exists yet.
- **`configuration`, `capabilities`, package/version metadata** on
  nodes. Named in `v0.1-architecture.md` §10 as future snapshot
  content; none has a real implementation behind it yet
  (`Component` still has none of these, per ADR-010's own deferral).
  Adding placeholder fields for content that doesn't exist would
  repeat the mistake ADR-010 explicitly avoided.
- **Any change to `Component`.** Ports were kept external to it in
  ADR-011; this ADR does not revisit that decision.

## Alternatives considered

- **Independent `to_json()`/`to_mermaid()` methods on `Module`, each
  walking `_modules` directly.** Rejected: exactly the "multiple
  representations that eventually disagree" failure mode this ADR
  exists to prevent.
- **`id(node)` or a generated UUID as node identity.** Rejected:
  process-local (`id()`) or non-deterministic (`uuid4()`) identity
  breaks reproducibility and makes two snapshots of the identical
  architecture incomparable — directly against R9 (reproducibility).
  The dotted path from `named_modules()` is already deterministic,
  already exists, and needed no new code to produce.
- **Calling this relationship `ArchitectureEdge`.** Rejected per
  Staff review: would misrepresent tree containment as general
  graph/data-flow semantics Step 8 doesn't have.
- **Discovering ports via `getattr(module, "input_ports", ())`-style
  duck typing.** Rejected: inventing an implicit discovery convention
  as a side effect of the snapshot ADR, rather than as its own
  deliberate design decision (which future component authors would
  need to know about and conform to), repeats the "invent a convention
  no one signed off on" risk explicitly flagged during design review.

## Testing strategy

- **Unit**: `ArchitectureNode`/`ArchitectureChild`/`ArchitectureSnapshot`
  construction, immutability (frozen dataclasses), equality.
- **Snapshot correctness**: a simple `Module` produces a single-node
  snapshot with the expected `id`/`name`/`component_type`; a nested
  tree (`Parent` with `child_a`/`child_b`, matching the existing
  `test_module.py` fixture) produces the expected nodes and
  `ArchitectureChild` relationships.
- **Determinism**: building a snapshot of the same architecture twice
  (two separate object graphs, same structure) produces `==` snapshots.
- **No execution**: a component whose `__call__`/`forward` raises
  `AssertionError` if invoked must snapshot successfully.
- **No arbitrary state access**: a component with a sensitive instance
  attribute (e.g. `self.api_key = "SECRET"`) — the snapshot (and its
  string repr, for defense in depth) must not contain the secret value,
  proven because `snapshot()` structurally never reads instance
  `__dict__`, not via a blacklist scan for the word "SECRET" (same
  category of lesson as the Step 7 provider-independence test: prefer
  a structural guarantee over a pattern-matched one).
- **Provider independence**: AST-based import check on
  `inspection.py`, following the Step 7 precedent (a plain substring
  scan false-positived on `"torch"` being contained in `"ragtorch"`
  there — the AST-based fix is reused as the standard pattern going
  forward, not re-derived).
- **Compatibility**: `Module.inspect()`'s existing test
  (`test_inspect_contains_counts_and_tree`) passes unmodified;
  `__repr__` (a separate, simpler existing representation) is
  untouched by this ADR.

## Benchmark strategy

Per ADR-009, `benchmarks/step8_architecture_snapshot.py`. Measures
`snapshot()` on a single node, a 10-node tree, and (if the existing
Step 1 `inspect()` 11-module benchmark tree is reused for direct
comparability) the same shape Step 1 already benchmarked — plus
`inspect()` before/after this ADR's internal rewrite, to confirm the
migration to a snapshot-backed implementation doesn't regress the
existing, already-tested performance characteristics. No hard threshold
is asserted; regression judgment is relative to the recorded baseline,
per the Step 5/6/7 methodology.

## Consequences

- Exactly one tree-walk produces the canonical architecture
  representation; `inspect()` (and any future renderer) consumes it
  rather than re-deriving it.
- Node identity is deterministic and reproducible across processes,
  supporting future evaluation/comparison use without inventing new
  identity infrastructure.
- The snapshot cannot leak component secrets structurally — not
  because of a filter, but because it never reads the state that would
  contain them.
- `ArchitectureNode.input_ports`/`output_ports` exist in the shape now,
  ready for a future port-aware population mechanism, without that
  mechanism being designed or built prematurely.
- Data-flow edges, serialization, and additional renderers remain
  explicit, named future work (not silently implied as "coming soon")
  — the next architectural step in this direction requires a real
  composition/graph contract, which this ADR deliberately does not
  attempt to substitute for.
