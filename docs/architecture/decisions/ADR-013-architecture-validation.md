# ADR-013: Architecture Snapshot Validation

## Status

Proposed

## Context

`ArchitectureSnapshot` (ADR-012) is a canonical description of a
`Module` tree's structure, but it is a plain, freely-constructible pair
of dataclasses (`nodes: tuple[ArchitectureNode, ...]`,
`children: tuple[ArchitectureChild, ...]`) with no invariant enforced
at construction. Auditing the current implementation directly (not
assumed) confirms this is a real gap, not a hypothetical one:

- `ArchitectureSnapshot(nodes=(...), children=(...))` can be
  constructed directly with duplicate node IDs, a child referencing a
  nonexistent parent, a node that is its own child, a node with two
  parents, zero or multiple roots, an orphaned node not reachable from
  any root, or a genuine cycle (`A → B → C → A`) — verified by hand-
  constructing each of these directly against the current dataclasses,
  all of which succeed silently today.
- `snapshot()` itself is not immune to the root cause. `Module`'s
  registration mechanism (`__setattr__`/`register_module`) does not
  prevent a cycle: `a.child = b; b.child = a` succeeds without error.
  Calling `snapshot(a)` (or even `a.named_modules()`, which `snapshot()`
  depends on) on such a tree raises `RecursionError`, not a clean,
  catchable failure — confirmed by direct reproduction, not assumed.
  This is a pre-existing gap in `Module`/`named_modules()` predating
  this ADR (Steps 1-4), out of scope to fix here (see Non-goals), but
  worth naming: a validator operating only on an already-built
  `ArchitectureSnapshot` cannot protect against this specific failure
  mode, because `snapshot()` crashes before producing one.

Since `ArchitectureSnapshot` is public API (exported from
`ragtorch.core`/`ragtorch`), any future consumer — a serializer
deserializing a snapshot from an external source, a hand-built test
fixture, a future format converter — can construct an invalid one
directly, not only via `Module.snapshot()`. A validation layer that
only defends against what `snapshot()` could theoretically produce
would miss this. `validate_snapshot()` must be a real, independent
check on the `ArchitectureSnapshot` data itself.

## Problem

We need a way to answer, deterministically and without executing
anything, "is this `ArchitectureSnapshot` structurally well-formed as a
tree?" — separately from execution, so architecture errors fail fast
at construction/validation time rather than surfacing as a confusing
failure partway through a future composition/execution step.

## Decision

### Public contract

```python
def validate_snapshot(snapshot: ArchitectureSnapshot) -> None:
    """Raise ValidationError if snapshot is not a well-formed tree.
    Returns None (no value) on success.
    """
```

Success is `None`; failure is `ValidationError` (already existing,
reused — see Error model below). No `ValidationResult` /
accumulated-errors object is introduced in this step — see Non-goals
and Alternatives considered.

### Location: `src/ragtorch/core/architecture.py`, not `inspection.py`

`inspection.py` *describes* architecture (ADR-012); this module
*validates* it. Keeping them separate mirrors the project's established
pattern of narrow, single-responsibility core modules (`ports.py`
describes boundaries, `component.py` describes the execution contract,
neither does the other's job) and leaves room for a future
`composition.py`/`execution.py` in the same family without any of them
growing into an "architecture does everything" module.

### A valid `ArchitectureSnapshot` is a non-empty rooted tree

Let `V` be the set of node IDs and `E` the set of parent→child
relationships. A snapshot is valid iff all ten of the following hold —
this is the frozen, precise contract, not an approximation of it:

1. **Non-empty**: `|V| >= 1`. A snapshot always originates from a
   `Module`, and a `Module` always has a root — an empty snapshot
   represents no real architecture and is rejected, not treated as a
   degenerate valid case.
2. **Unique node IDs**: no two nodes share an `id`.
3. **Children reference existing nodes**: every `ArchitectureChild`'s
   `parent_id` and `child_id` both name a node present in `V`. Checked
   *before* any parent-counting or reachability step (see Algorithm
   below) — otherwise a dangling reference could surface as a
   confusing "unreachable node" failure instead of naming the actual
   problem.
4. **No self-containment**: `parent_id != child_id` for every child
   relationship.
5. **At most one parent per non-root node**: no `child_id` appears as
   the child in more than one `ArchitectureChild`. This is the rule
   that actually keeps the structure a tree rather than a DAG — a
   one-root check alone is insufficient. Concrete counter-example,
   verified by direct construction: `A → B`, `A → C`, `B → D`,
   `C → D` has exactly one root (`A`) and zero duplicate IDs, but `D`
   has two incoming edges (`parent_by_child` would need `D`'s parent
   to be both `B` and `C`) — a diamond, not a tree. Rule 6 (root count)
   does not catch this on its own; Rule 5 does.
6. **Exactly one root**: exactly one node has zero incoming child
   relationships (is never a `child_id`).
7. **Full reachability**: every node in `V` is reachable from the root
   by following child relationships. An orphaned node (present in
   `nodes`, absent from the reachable set) is rejected — this also
   catches a *disconnected* cycle (e.g. valid subtree `A → B` plus an
   unrelated cycle `C → D → C`): `A` is the sole root, but `C`/`D` are
   never reached from it.
8. **Containment only, never data-flow**: `ArchitectureChild` means
   "this node structurally contains that node" (a `Module`'s
   registered child), never "this node's output feeds that node's
   input." This ADR does not (and, given ADR-012's own scope, cannot)
   validate data-flow compatibility — see Non-goals. Frozen here
   explicitly because Step 10+'s composition/Block/data-flow-edge work
   must not silently conflate the two concepts `ArchitectureChild` was
   deliberately kept separate from.
9. **Read-only**: validation never mutates, deduplicates, reorders, or
   repairs the snapshot (see Decision, below).
10. **Deterministic outcome**: `None` on success; `ValidationError` on
    the first violation found, in the fixed order given by the
    Algorithm section — the same invalid snapshot always fails with
    the same error.

Rules 2 (no self-loop), 5 (≤1 parent), and 6 (exactly 1 root) together
rule out cycles reachable from the root without a separate DFS
cycle-detector: a genuine cycle (`A → B → C → A`) has zero nodes with
zero incoming edges, so it fails Rule 6 (0 roots, not exactly 1) —
verified directly by hand-constructing this exact 3-node cycle. A
*disconnected* cycle is instead caught by Rule 7 (reachability), not
Rule 6, since the connected part of the graph can still have exactly
one legitimate root. Both cases are proven by dedicated tests, not
merely inferred from the other rules holding — per the project's
standing rule that a load-bearing assumption should be a test, not a
comment. No separate cycle-detection algorithm is implemented; adding
one would be redundant for this specific tree contract (see
Alternatives considered).

### Algorithm and complexity: O(N + E)

Validation proceeds in this fixed order, so a caller always learns the
*first* structural problem in a consistent, predictable sequence rather
than whichever rule happened to be checked last:

```text
1. |V| == 0?                                    -> ValidationError (empty)
2. build nodes_by_id; duplicate id encountered?  -> ValidationError
3. every child's parent_id/child_id in nodes_by_id? -> ValidationError (dangling)
4. any parent_id == child_id?                    -> ValidationError (self-containment)
5. build parent_by_child; any child_id seen twice?  -> ValidationError (multiple parents)
6. exactly one node with zero incoming edges?       -> ValidationError (root count)
7. reachability walk from that root covers all of V?  -> ValidationError (unreachable nodes)
8. all checks passed                                     -> None
```

Each step is a single pass over `nodes` (O(N)) or `children` (O(E));
the reachability walk (step 7) is a single BFS/DFS over a
`children_by_parent: dict[str, list[str]]` index built once, visiting
each node and edge at most once — O(N + E) total, O(N) additional
space for the lookup structures. No rule re-scans the full `children`
collection per node.

### Error model: reuse `ValidationError`

`ragtorch.core.errors.ValidationError` ("Raised when input/output
validation fails") is exactly this failure category and is already the
convention `ports.py` (ADR-011) established for invalid architecture
metadata. No new exception type is introduced. Distinguished from the
existing `RegistryError` (`Module.register_module`'s duplicate-name
check): `RegistryError` is a live, single-parent-scoped check enforced
during `Module` construction (can two children of *this* module share a
name?); `validate_snapshot()` is a whole-snapshot, post-hoc structural
check operating on already-built `ArchitectureSnapshot` data,
independent of whether it came from a real `Module` tree at all — the
two serve related but distinct purposes and neither substitutes for the
other. Error messages name the specific offending id(s) (e.g.
`"Duplicate architecture node id: 'root.retriever'"`), not a generic
"invalid architecture" string.

### Read-only: validation never mutates or repairs

`validate_snapshot()` only reads `snapshot.nodes`/`snapshot.children`
and any lookup structures built from them; it never modifies the
snapshot, deduplicates, reorders, drops orphans, or synthesizes a
missing root. An invalid snapshot is rejected, not silently corrected.

## Non-goals

### Validation validates representation, not construction

This principle is frozen explicitly, not left implicit:

```text
Module construction -> Module registration -> snapshot() ->
ArchitectureSnapshot -> validate_snapshot()
```

Step 9 validates at the **snapshot boundary** — the data produced by
`snapshot()` (or built by hand) — and nowhere upstream of it.
`validate_snapshot()` does not, and structurally cannot, make `Module`
construction/registration itself safe against producing a malformed
tree (see the cycle-registration gap below). This is a deliberate
scope boundary, not an oversight: it keeps `validate_snapshot()`'s job
small and well-defined, and leaves `Module`-level safety as a distinct
future decision if one is ever judged worth making, rather than an
emergency patch bolted onto this ADR.

Also explicitly deferred, not part of this decision:

- **Data-flow validation** ("does this retriever's output type match
  that reranker's input port"). The snapshot has no data-flow concept
  to validate (ADR-012 Non-goals) — Rule 8 (Decision) makes explicit
  that `ArchitectureChild` means containment only; none of Rules 1-10
  concern `input_ports`/`output_ports` compatibility.
- **Fixing the underlying `Module` cycle-registration gap.**
  `a.child = b; b.child = a` succeeding, and `named_modules()`
  subsequently `RecursionError`-ing, predates this ADR and is out of
  scope here — `validate_snapshot()` operates on an already-built
  `ArchitectureSnapshot`; it cannot validate a snapshot that could not
  be constructed in the first place. Worth a future ADR if judged worth
  fixing at the `Module` level.
- **Execution planning, graph scheduling, DAG algorithms.** Validation
  answers "is this a well-formed tree," not "in what order should this
  execute" — that is a future composition/execution step's problem.
- **Automatic architecture repair.** See Decision (read-only).
- **`ValidationResult` with accumulated/multiple errors.** `None` on
  success, single `ValidationError` (with a maximally specific message
  about the *first* violation found) on failure. If a future need for
  "report every structural problem at once" is demonstrated, that is an
  additive API alongside `validate_snapshot()`, not a redesign of it —
  see Alternatives considered.
- **A `Module.validate()` convenience method.** Start with
  `validate_snapshot(module.snapshot())`; a convenience wrapper is
  additive if repeatedly needed later, mirroring how `Module.snapshot()`
  itself was added only once `snapshot()` proved useful, not
  speculatively (see ADR-012).
- **Third-party graph libraries** (NetworkX, etc.), a graph database, or
  a generic type-inference system.

## Alternatives considered

- **`bool` return instead of raise-on-failure.** Rejected: `if
  validate_snapshot(snapshot):` does not communicate *why* validation
  failed, and every real caller of a validation function needs to
  report the specific problem, not just a yes/no. Raising with a
  specific message is strictly more useful and costs nothing extra for
  a caller that only wants to know pass/fail (a bare `try`/`except` is
  no more code than an `if`).
- **`ValidationResult(valid: bool, errors: list[str])` with accumulated
  errors from the start.** Rejected for this step: no evidence yet that
  RAG-MODULE users need "see all N problems at once" rather than
  "fail fast on the first problem" — introducing the richer object
  before that need is demonstrated repeats the mistake ADR-010 avoided
  with `Component.capabilities`/`configuration`. `validate_snapshot()`
  raising on the first violation is the smaller, provably sufficient
  contract; the richer form remains a strict addition later.
- **Validating inside `snapshot()` itself, so every snapshot is
  guaranteed valid by construction.** Rejected: `snapshot()` built from
  a real `Module` tree is already tree-shaped by construction (barring
  the pre-existing cycle-registration gap, itself out of scope — see
  Non-goals); folding validation into `snapshot()` would pay validation
  cost on every call regardless of whether the caller needs the
  guarantee, and would not protect a snapshot built by hand or
  deserialized from elsewhere, which is exactly the case this ADR's
  Context section identifies as the real risk. Keeping validation
  separate and explicit (`validate_snapshot(snapshot)`) matches the
  project's established "validation is a separate concern from
  execution" principle, extended to snapshot construction as well.
- **Putting validation logic inside `inspection.py`.** Rejected: see
  Decision (Location) — keeps single-responsibility modules distinct,
  consistent with `ports.py`/`component.py` already being separate.

## Security

`validate_snapshot()` reads only `ArchitectureNode`/`ArchitectureChild`
fields already present in the snapshot (`id`, `parent_id`, `child_id`)
— it never touches a live `Module` instance, never calls `module(...)`,
never reads `vars()`/`__dict__`, never evaluates annotations, and never
deserializes untrusted data (it validates already-in-memory
dataclasses, not a serialized format — no such format exists yet, per
ADR-012 Non-goals). This is a narrower surface than `snapshot()` itself
needs, since validation never touches a `Module` at all.

## Dependency review

Zero new runtime dependencies. `architecture.py` imports only
`ragtorch.core.errors` and `ragtorch.core.inspection` (both existing
internal modules) — no `networkx`, no graph library, no schema/
validation framework. The tree sizes RAG-MODULE architectures are
expected to have do not warrant one.

## Compatibility

No changes to `Component`, `Module.__call__`, `ExecutionEngine`,
`ExecutionContext`, `Sequential`, `ports.py`, or `inspection.py`
(`ArchitectureSnapshot` and friends are read, not modified). All
pre-existing tests are expected to pass unmodified. The only new public
surface is `validate_snapshot()` (and its home module).

## Testing strategy

- **Valid cases**: one-node tree; two-node tree (`A → B`); deep tree
  (`A → B → C → D`); branching tree (`A → {B, C, D}`) — all must
  return `None`, not raise.
- **Invalid cases**, each independently triggering `ValidationError`
  and, per the fixed algorithm order, each isolated so it's the *only*
  violation present (so the test proves that specific rule, not an
  earlier one in the sequence firing first):
  - empty snapshot (Rule 1);
  - duplicate node ID (Rule 2);
  - dangling child reference — `parent_id` or `child_id` naming a node
    absent from `nodes` (Rule 3);
  - self-containment, `parent_id == child_id` (Rule 4);
  - **multiple parents via a diamond** — `A → B`, `A → C`, `B → D`,
    `C → D`: exactly one root, zero duplicate IDs, yet `D` has two
    parents (Rule 5) — the concrete counter-example proving "one root"
    alone is an insufficient tree check;
  - zero roots (a cycle, e.g. `A → B → C → A` — Rule 6);
  - multiple roots (two disjoint single-node trees, e.g. `A` and `B`
    both present with no relationship between them — Rule 6);
  - a disconnected node reachable from nothing (`A → B` plus isolated
    `C`, present in `nodes` but no child relationship at all — Rule 7);
  - a **disconnected cycle** — valid subtree `A → B` plus an unrelated
    cycle `C → D → C`: `A` is a legitimate sole root, but `C`/`D` are
    unreachable from it (Rule 7, not Rule 6 — proves reachability
    catches what root-counting alone would miss).
- **Read-only**: validating a snapshot does not mutate its `nodes`/
  `children` tuples (trivially true for frozen dataclasses, but
  asserted directly rather than only inferred from immutability).
- **Determinism**: validating the same snapshot twice produces the same
  outcome and (for the failure case) the same error message content.
- **Integration**: a real `Module` tree (e.g. `root` containing
  `retriever` containing `reranker`, and `generator`) →
  `module.snapshot()` → `validate_snapshot()` succeeds, with no LLM,
  database, provider, network, or model execution involved — proving
  the validator accepts what the real system actually produces, not
  only hand-built dataclass fixtures. `module.inspect()` is called
  afterward in the same test to confirm the already-existing
  snapshot-backed rendering (ADR-012) still works on a now-validated
  snapshot, without `inspect()` itself being changed to call
  `validate_snapshot()` — that remains the caller's explicit choice,
  not an implicit behavior this ADR adds.
- **Complexity**: a benchmark (not a unit test) demonstrating
  near-linear scaling from 1 to 1,000 nodes, per Step 9's benchmark
  requirement.

## Consequences

- Future composition/`Block`/execution-planning steps can call
  `validate_snapshot(module.snapshot())` as a fail-fast precondition
  rather than each reinventing structural validation or discovering
  architecture errors mid-execution.
- `ArchitectureSnapshot` remains a plain, freely-constructible data
  type (no constructor-level enforcement) — validation stays opt-in and
  explicit, consistent with keeping snapshot construction cheap and
  side-effect-free for callers who don't need the guarantee.
- The pre-existing `Module` cycle-registration gap (`a.child = b;
  b.child = a` succeeding, then `RecursionError`-ing on traversal) is
  now a documented, named limitation rather than an undiscovered
  landmine — tracked here as explicitly out of scope, not silently
  ignored.
