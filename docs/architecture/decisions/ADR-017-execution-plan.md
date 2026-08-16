# ADR-017: Execution Plan

## Status

Proposed

## Context

After Step 12, `CompositionGraph` (ADR-016) can answer "is this
collection of nodes and directed `Connection`s a structurally valid
composition?" — but a structurally valid graph does not by itself tell
a runtime what order to run nodes in. A DAG such as:

```text
A → B
A → C
B → D
C → D
```

is a valid `CompositionGraph`. Neither `A, B, C, D` nor `A, C, B, D` is
privileged by the graph's own data (`nodes`/`connections` preserve
construction order, not execution order) — both are valid topological
orderings, and nothing today picks one deterministically or represents
"D depends on B and C" as a fact a caller can consume without
re-deriving it from `connections` every time.

Meanwhile, `ExecutionEngine` (ADR-006/ADR-008) already exists and
coordinates `Run`/`Trace`/`MetricsCollector` around a single `Module`
call — it has real, established observability responsibility, but no
concept of a multi-node graph, dependency ordering, or scheduling.
`Sequential` (Step 1) is a genuinely different, simpler primitive: an
already-linear chain of `Module`s executed in registration order,
implemented as a plain Python loop. It has no dependency graph to
derive an order from — its order *is* its construction — and this ADR
does not change that.

**This ADR does not build an executor, a scheduler, or async/parallel
execution.** It answers one narrower question: given a valid
`CompositionGraph`, what is the deterministic, dependency-respecting
execution order and dependency metadata — represented as data, not as
code that runs anything? Confirmed with the project owner before
drafting, following an 18-question audit (recorded in full in the
project's Step 13 planning discussion) that deliberately separated
*planning* (this ADR) from *scheduling/execution* (explicit future
work).

```text
Component (ADR-010)
      |
      v
GraphNode / Connection (ADR-015/ADR-016)
      |
      v
CompositionGraph (ADR-016)
      |
      v
ExecutionPlan (this ADR)
      |
      v
Future: sync / async / parallel executor
      |
      v
ExecutionEngine (ADR-006/ADR-008) -- Run / Trace / Metrics
```

## Problem

We need a value type representing a deterministic topological ordering
of a `CompositionGraph`'s nodes, together with each node's direct
dependencies — computed once from the graph's existing, already-valid
structure, containing no runtime objects (no `Component` instances, no
callables, no engine references) so it remains safe to inspect, log,
cache, or eventually serialize without accidentally capturing
execution state or secrets.

## Open questions this ADR must decide before any code is written

The Step 13 audit raised 18 questions. Each is given an explicit
architectural decision below, with the rejected alternative stated,
not merely the chosen answer. **A decision here is a stated intent,
not a proven guarantee** — it becomes a guarantee only once
implementation, tests, benchmark, and CI each independently confirm
the code actually satisfies it (per the project's standing lifecycle:
ADR decision → implementation → tests → benchmark → CI → post-merge
CI). Nothing in this section should be read as "already true of the
system" until that chain completes. The most consequential of the 18
is Q7/Q8 (what shape does the plan take), so it is argued as a genuine
fork rather than assumed.

**Q1/Q2 — What is `ExecutionPlan`, and does deriving it mutate the
graph?** It is data describing a deterministic ordering, derived from
an existing `CompositionGraph` without modifying it. Not contested —
follows directly from `CompositionGraph`'s own immutability guarantee
(ADR-016); there is no alternative under consideration where deriving
a plan could mutate its source.

**Q3 — Does planning execute components?** No. Not contested — every
prior structural type in this codebase (`ArchitectureSnapshot`,
`CompositionGraph`) already established "construction/derivation never
executes a component" as a hard rule; nothing about deriving an
ordering needs to violate it.

**Q4 — Does planning require `ExecutionEngine`?** No — the dependency
direction is one-way, `execution_plan.py` depending on
`composition.py`, never the reverse. See "No runtime objects in the
plan," ground 3, below.

**Q5 — Any valid topological order, or a deterministic one?**
Deterministic. This is a real choice, not a formality: a
nondeterministic order would satisfy every dependency constraint just
as validly, but would make two calls to `plan()` on the same graph
potentially produce different, though equally "correct," orderings —
which breaks reproducibility, test assertions, caching by plan
content, and future diffing. Argued in full under "Ordering algorithm"
below.

**Q6 — What breaks ties among simultaneously-ready nodes?** This is
the second most consequential open question, argued in full under
"Ordering algorithm" and in Alternatives (the rejected lexicographic
option).

**Q7/Q8 — Does the plan hold bare node ids, or ids plus dependency
metadata?** This is the fork the Step 13 review specifically flagged
as not yet settled. Both sides:

- *A minimal plan is `tuple[str, ...]` — ordered ids only, nothing
  else.* This is the smaller public surface: fewer types, nothing to
  keep synchronized with the graph, and a caller who wants a specific
  node's dependencies can already get them by re-querying
  `CompositionGraph.connections` directly — the graph remains the one
  source of truth for dependency facts, and the plan is purely "here
  is a safe order to iterate the graph's nodes in."
- *A richer plan is `tuple[ExecutionStep, ...]`, each step carrying
  `node_id` plus its direct `dependencies`.* This makes the plan
  usable on its own — without also holding a reference to the source
  `CompositionGraph` — by a future consumer that wants readiness
  detection (which steps have all dependencies already satisfied) for
  parallel scheduling, or that wants to serialize/cache/transmit the
  plan independently of the graph it came from. The cost is a second
  type in the public API and dependency data that must remain
  consistent with the graph's own `connections` (mitigated: `plan()`
  computes both from the same source in one pass, so there is no
  window where they could disagree).

  **Decision: the richer form (`ExecutionStep` with `dependencies`).**
  The deciding factor is not "more fields are always better" — it is
  that a future executor is the actual, named reason this ADR exists
  (see Context), and an executor needs readiness information to do
  anything beyond replaying a fixed serial order. If `ExecutionPlan`
  shipped as bare ids now, adding dependency data later would not be a
  clean additive change — it would require either wrapping the
  existing `tuple[str, ...]` in a new type (breaking every consumer
  that pattern-matched on the old shape) or bolting dependency lookup
  onto `ExecutionPlan` as a separate method that re-derives it from a
  graph reference the plan doesn't otherwise need to hold. Both are
  worse than deciding the richer shape now, while nothing depends on
  the API yet and the cost of being wrong is zero. This mirrors the
  precedent already set for `Connection` over a raw tuple (ADR-015)
  and is treated with the same seriousness — not asserted, argued.

**Q9 — Is `ExecutionStep` public, not just an internal detail of
`plan()`?** Yes — if `dependencies` is worth computing (per Q7/Q8), it
is worth exposing typed rather than forcing every consumer to
re-parse a less structured representation.

**Q10 — Node identity semantics?** `ExecutionStep.node_id` is exactly
`GraphNode.id` — no new identity system, no re-derivation. Not
contested — inventing a second id scheme for the same node would
violate the single-source-of-truth discipline every layer since
ADR-011 has followed.

**Q11 — Empty graph behavior?** `plan()` of an empty graph returns an
empty plan, no exception. Not contested — an empty `CompositionGraph`
is already valid (ADR-016), so a plan for it should be the trivial
valid case, not a special error.

**Q12 — Disconnected graphs?** Supported, no special-casing —
`CompositionGraph` itself does not require connectedness (ADR-016 has
no such invariant), so `plan()` introduces none either.

**Q13 — Does planning re-run graph validation (cycles, referential
integrity)?** No — trusts `CompositionGraph.__post_init__`'s existing
guarantee. Argued in Alternatives below, since "re-validate defensively
anyway" is a real, rejected alternative, not an oversight.

**Q14 — Async/parallelism in this step?** No, but the data shape must
not foreclose it. Argued under "Parallelism... are explicit future
work" below.

**Q15 — Serialization implemented in this step?** No — but the
no-runtime-objects rule (ground 2 below) is chosen specifically so a
future serializer is not blocked by this step's data model choices.

**Q16 — Relationship to `Sequential`?** None — `Sequential` is
untouched, unrelated, and remains its own simpler primitive. Not
contested; see Non-goals.

**Q17 — Relationship to `ExecutionEngine`?** None yet — `plan()` does
not import `ragtorch.core.engine`, and `ExecutionEngine` is not
modified. See Non-goals.

**Q18 — Failure semantics if handed something graph-shaped but
invalid?** Out of scope for this version: the public contract accepts
a `CompositionGraph`, whose own constructor already refuses to exist
in an invalid state (ADR-016) — there is no code path today by which
`plan()` receives an "invalid `CompositionGraph`," so no new failure
mode is defined for one. If a future change makes that possible (e.g.
an internal fast-path that bypasses `__post_init__`), it is a
deliberate, separate decision at that time, not implied here.

## Decision

### Naming and location: `ExecutionPlan`/`ExecutionStep`, `src/ragtorch/core/execution_plan.py`

A new module, not an addition to `composition.py` or `engine.py`: this
is a genuinely new concern (deriving an executable ordering), not a
thin wrapper over an existing function. `execution_plan.py` (not
`plan.py` or `scheduler.py`) names exactly what this module produces,
avoiding future collision with an eventual `ExecutionEngine`-adjacent
scheduling concept.

### Public contract

The shape below is the resolution of Q7/Q8/Q9 above (the richer
`ExecutionStep` form, chosen over bare `tuple[str, ...]`) — restated
here as the concrete contract, not re-argued.

```python
@dataclass(frozen=True)
class ExecutionStep:
    """One node's position within a plan: its identity and its direct
    dependencies, both by graph-local node id.

    dependencies contains only direct predecessors (nodes with a
    Connection whose target_node_id is this step's node_id) -- not the
    full transitive dependency set. A consumer that needs transitive
    dependencies derives them by walking the plan; ExecutionStep does
    not precompute or cache that separately.
    """

    node_id: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    """A deterministic topological ordering of a CompositionGraph's nodes.

    steps[i].node_id names a GraphNode.id from the source graph; steps
    is ordered such that every dependency of steps[i] appears at some
    index j < i. Contains no Component instances, no callables, and no
    ExecutionEngine/ExecutionContext reference -- planning is pure data
    derived from CompositionGraph's existing structure.
    """

    steps: tuple[ExecutionStep, ...]


def plan(graph: CompositionGraph) -> ExecutionPlan:
    """Derive a deterministic ExecutionPlan from a valid CompositionGraph.

    Does not validate graph -- CompositionGraph.__post_init__ (ADR-016)
    already guarantees acyclicity, referential integrity, and no
    duplicate connections; plan() trusts that guarantee rather than
    re-checking it, the same single-source-of-truth discipline
    is_compatible()/check_connection()/Connection/CompositionGraph
    already established layer by layer. Never calls any node's
    component.__call__. Does not mutate graph.
    """
```

`plan()` is a free function, not a `CompositionGraph` method — see
"Why `plan()` is a free function, not a graph method" below.

**Naming: `plan(graph)`, not `ExecutionPlan.from_graph(graph)` or
`create_execution_plan(graph)`.** Considered explicitly, not defaulted
to out of habit: `ExecutionPlan.from_graph()` (a classmethod
constructor) was rejected because it implies `ExecutionPlan` might
gain other `from_*` constructors, which invites exactly the kind of
speculative API surface this project avoids elsewhere — there is
currently exactly one way to produce a plan, from a graph, so a plain
function says that directly. `create_execution_plan()` was rejected as
needlessly verbose for a `ragtorch.core` function whose single
argument type already makes its purpose unambiguous at the call site
(`plan(graph)` reads no less clearly than `create_execution_plan(graph)`
once imported, and every other free function in this codebase
following the same pattern — `snapshot()`, `is_compatible()`,
`check_connection()` — uses a short, undecorated verb or predicate
name, not a `create_`/`build_`-prefixed one). `plan()` matches that
established naming convention.

### Ordering algorithm: deterministic Kahn's algorithm, tie-broken by graph declaration order

Resolves Q5/Q6 above. Computed via the same iterative Kahn's-algorithm shape `CompositionGraph`
already uses for cycle detection (ADR-016) — not a new algorithm
family, and not `networkx`. The queue of "ready" nodes (in-degree zero)
is processed in **graph node declaration order** whenever more than one
node is ready simultaneously: `graph.nodes` is an ordered tuple with a
guaranteed-deterministic iteration order (ADR-016's own determinism
invariant), so `plan()` reuses that existing ordering as its
tie-breaker rather than inventing a second ordering concept (e.g.
lexicographic by `node_id`). Two independently-constructed but
value-equal `CompositionGraph`s therefore always produce value-equal
`ExecutionPlan`s.

### `ExecutionStep.dependencies` holds direct predecessors only, by node id (not transitive)

Not the full transitive closure, and not `Connection`/`GraphNode`
instances. Direct predecessors are exactly what `plan()` computes as a
side effect of Kahn's algorithm (each node's in-edges); the transitive
closure is a derived property any consumer can compute from the full
`steps` sequence if it needs one, not something `ExecutionPlan` commits
to maintaining as a second, potentially-inconsistent representation.
Storing node ids rather than `GraphNode`/`Connection` objects keeps
`ExecutionPlan` free of `Component` instances — see "No runtime
objects in the plan" below.

**`dependencies`' own internal ordering is also deterministic, not
merely the top-level `steps` sequence.** A node with multiple
predecessors (e.g. `D` depending on both `B` and `C`) must produce the
same `dependencies` tuple — same order, every time — across repeated
calls to `plan()` on the same or an equal graph; otherwise two
constructions of `D`'s step could differ as `(B, C)` in one run and
`(C, B)` in another, which would silently break `ExecutionPlan`
value-equality (see "Plan and step equality" below) even when the
underlying graph is unchanged. `plan()` builds each step's
`dependencies` by iterating the source graph's own `connections` tuple
in its existing, already-deterministic order (ADR-016) and appending
each matching predecessor as it is found — not by iterating a `set` or
`dict` whose iteration order is an implementation detail. This is the
same "reuse the graph's own established order rather than inventing a
second one" reasoning already applied to the `steps`-level tie-break
below, applied one level deeper.

### Plan and step equality, immutability, and graph retention

Resolves the 13A adversarial-review items B/C/D/E/G/H (Staff review
prior to committing this ADR).

- **Equality is value equality, not identity.** `ExecutionStep`/
  `ExecutionPlan` are plain frozen `@dataclass`es, so Python generates
  `__eq__` from their fields by default — two `ExecutionPlan`s with
  equal `steps` tuples (which in turn requires equal `node_id` and
  equal `dependencies` on every step, in the same order per the
  determinism guarantee above) compare `==`. This is deliberate, not
  incidental: it is exactly what makes `assert plan == expected_plan`
  a usable, exact regression-test assertion, and what makes a plan a
  legitimate candidate for a future cache keyed by plan content —
  consistent with every other value type in this codebase
  (`Connection`, `ArchitectureChild`, `CompositionGraph` all already
  rely on the same default dataclass equality).
- **Immutability is structural, not just documented.** `frozen=True`
  on both dataclasses means `plan.steps = (...)` and
  `step.dependencies = (...)` both raise `AttributeError` at
  the language level — the same guarantee `CompositionGraph`/`GraphNode`
  already provide, continued here rather than newly invented.
  `steps`/`dependencies` are tuples, not lists, so there is no mutable
  container reachable from a constructed `ExecutionPlan` at all — not
  `plan.steps.append(...)` (tuples have no `append`), not
  `step.dependencies += (...)` on the stored value (dataclass field
  reassignment is blocked by `frozen=True` regardless).
- **`ExecutionPlan` does not retain a reference to its source
  `CompositionGraph`.** The public contract is `ExecutionPlan(steps:
  tuple[ExecutionStep, ...])` — no `graph` field. `plan()` is a
  pure function `CompositionGraph -> ExecutionPlan`: information flows
  one way, at the moment `plan()` is called, and nothing about the
  resulting `ExecutionPlan` value depends on the `CompositionGraph`
  object continuing to exist or remaining unchanged. This was
  reconsidered specifically against the alternative of
  `ExecutionPlan(graph=graph, steps=...)`, which was rejected: holding
  the graph would (a) reintroduce exactly the kind of coupling "No
  runtime objects in the plan" below argues against extending to
  the graph as well, (b) complicate a future serializer, which would
  either have to serialize the whole graph redundantly or special-case
  skipping the field, and (c) imply a "does the plan track live graph
  changes" question that has no good answer given both types are
  immutable values in the first place — there is nothing for the plan
  to "track."
- **Snapshot semantics follow directly from immutability on both
  sides, and are stated explicitly rather than left implicit.** Given
  `graph1`, `plan1 = plan(graph1)`, and later `graph2 =
  graph1.add_node(...)`: `plan1` is unaffected by `graph2`'s existence
  — not because `plan()` does anything special to defend against it,
  but because `graph1` itself is never mutated by `add_node()`
  (ADR-016) and `plan1` never held a reference to `graph1` to begin
  with (see previous point). If a caller wants a plan reflecting
  `graph2`, they call `plan(graph2)` again, producing an independent
  `ExecutionPlan` value with no relationship to `plan1` beyond
  possibly comparing equal if the two graphs happen to produce the
  same ordering.
- **Target complexity is O(V + E).** `plan()` is a single pass building
  an adjacency/in-degree structure from `connections` (O(E)) followed
  by Kahn's algorithm (O(V + E)) — the same complexity class
  `CompositionGraph`'s own cycle detection already achieves (ADR-016,
  empirically confirmed by the Step 12 benchmark's near-linear scaling
  results). No step in `plan()` is quadratic in the number of nodes or
  connections; the Step 13 benchmark (below) exists specifically to
  confirm this empirically rather than by algorithm-design argument
  alone, following the precedent set by Step 12's own benchmark
  catching a real scaling defect that no amount of small-graph
  correctness argument would have revealed.
- **No independent re-implementation of graph validity.** `plan()`
  computes exactly one thing `CompositionGraph` does not already
  compute — an ordering — from data `CompositionGraph` already
  guarantees is valid (acyclic, referentially intact, no duplicate
  edges). It does not re-run cycle detection, does not re-check
  referential integrity, and does not re-detect duplicate connections;
  doing so would risk exactly the "graph says valid, planner says
  invalid" drift scenario a from-scratch reimplementation could
  introduce if the two algorithms were ever expressed differently or
  updated independently. This is the same single-source-of-truth
  discipline stated in Q13 above and in Alternatives below, restated
  here as a named, permanent architectural guarantee rather than only
  a rejected alternative.

### No runtime objects in the plan

`ExecutionStep`/`ExecutionPlan` contain only `str` node ids and tuples
thereof — no `GraphNode`, no `Component`, no callable, no
`ExecutionContext`/`ExecutionEngine` reference. This is deliberate on
three grounds:

1. **Security**: a plan that never holds a `Component` instance cannot
   accidentally carry a provider client, API key, or open connection
   into a log line, cache entry, or future serialized form — the same
   "don't collect it in the first place" philosophy
   `ArchitectureSnapshot`/`snapshot()` established in ADR-012, applied
   here to a type that (unlike `ArchitectureSnapshot`) sits directly
   upstream of real execution.
2. **Serialization-readiness**: a future JSON (or other) serializer for
   `ExecutionPlan` needs to handle only strings and tuples — no
   `Component` instances mean no premature decision about how to
   (or whether to) serialize arbitrary user-defined components. This
   ADR does not implement serialization; it avoids making the data
   model incompatible with it later.
3. **Decoupling from the engine**: `plan()` never imports
   `ragtorch.core.engine`, so the planner is usable and testable with
   no `ExecutionEngine` involved at all — the dependency direction is
   `composition.py` → `execution_plan.py`, never
   `execution_plan.py` → `engine.py`.

### `plan()` never executes a component

`plan()` reads only `GraphNode.id` and `Connection`'s
`source_node_id`/`target_node_id` fields (both already validated by
`CompositionGraph`/`Connection`'s own construction). It never calls
`component.__call__` or any descendant of it — the same security
posture established for `snapshot()` (ADR-012) and every
`CompositionGraph` operation (ADR-016), continued here for the first
type that sits directly upstream of eventual execution.

### `plan()` does not mutate `graph`

`CompositionGraph` is already immutable (ADR-016); `plan()` reads it
and returns a new `ExecutionPlan`, never modifying `graph.nodes` or
`graph.connections`.

### Why `plan()` is a free function, not a graph method

`graph.plan()` would read naturally, but a free function
`plan(graph)` is chosen instead so that `CompositionGraph`'s own
public surface (ADR-016) does not grow with every new *consumer* of
graph data — `ArchitectureSnapshot` similarly is consumed by
`Module.inspect()` via a free function (`snapshot()`) rather than
gaining an `inspect()`-shaped method of its own beyond what already
existed. This also keeps the dependency direction explicit and
one-way: `execution_plan.py` imports from `composition.py`,
`composition.py` never imports from `execution_plan.py`.

### Disconnected graphs, empty graphs, and root nodes are all ordinary cases

- `CompositionGraph` does not require connectedness (ADR-016 has no
  such invariant); `plan()` does not add one. Two disconnected
  components each get a valid partial ordering within the single
  overall `ExecutionPlan` — Kahn's algorithm handles multiple
  independent "ready" subsets without any special-casing.
- `plan(CompositionGraph(nodes=(), connections=()))` returns
  `ExecutionPlan(steps=())` — no special error. An empty graph is a
  degenerate but valid graph (ADR-016 already allows it); a plan for
  it is trivially the empty plan.
- A node with `dependencies == ()` is a root — nothing about
  `ExecutionStep` privileges roots or treats them specially beyond
  naturally having no dependencies; this is exactly why
  `dependencies` is part of the per-step data rather than a separate
  "roots" field.

### Parallelism, async, and layered/level-based grouping are explicit future work, representable but not implemented

`ExecutionStep.dependencies` is sufficient for a future scheduler to
derive "which steps are mutually independent and could run
concurrently" (any steps whose dependencies are already satisfied), so
this ADR does not foreclose that future work — but it does not compute
or expose a grouped/leveled representation itself. Adding one later
(e.g. `ExecutionPlan.levels() -> tuple[tuple[str, ...], ...]`) is
additive; this version deliberately ships only the flat, deterministic
`steps` sequence a synchronous consumer needs.

## Non-goals

Explicitly deferred, not part of this decision:

- **An executor.** No `execute(plan)` function or method, synchronous
  or otherwise, is introduced. `ExecutionPlan` is data a future
  executor consumes.
- **`ExecutionEngine` integration.** `execution_plan.py` does not
  import `ragtorch.core.engine`; `ExecutionEngine` is not modified to
  accept or produce an `ExecutionPlan`.
- **Parallel or async execution.** Not implemented; see "Parallelism...
  are explicit future work" above for why the data model does not
  foreclose it.
- **Retries, timeouts, resource hints, or any other per-step
  scheduling metadata.** `ExecutionStep` carries exactly `node_id` and
  `dependencies`; additional fields are a deliberate, separate, future
  addition once a real consumer justifies them (mirroring ADR-010's
  reasoning for keeping `Component` minimal).
- **Serialization.** No JSON/other format for `ExecutionPlan` is
  defined; the data model is kept serialization-*friendly* (no runtime
  objects) without implementing serialization itself.
- **Turning `Sequential` into a graph-derived primitive.** `Sequential`
  remains its own simple, linear, registration-order composition — it
  does not gain a `CompositionGraph`/`ExecutionPlan` relationship in
  this step, and continues to work exactly as it does today with zero
  lines touched.
- **Integration with `ArchitectureSnapshot`.** `plan()` consumes only
  `CompositionGraph`, never `ArchitectureSnapshot` — the two identity
  systems (`GraphNode.id` vs. `ArchitectureNode.id`) remain
  independent, per ADR-016's own established boundary.
- **Re-validating graph structure.** `plan()` trusts
  `CompositionGraph`'s existing acyclicity/referential-integrity
  guarantees rather than re-checking them — see "Ordering algorithm"
  and Alternatives below.
- **A `Block` type.** Still not introduced; `ExecutionPlan` is
  consumed by a future `Block`/executor, not built here.

## Alternatives considered

`Alternatives` below covers decisions not already argued as a fork in
"Open questions" above — the bare-`tuple[str, ...]` alternative to
`ExecutionStep` is covered there (Q7/Q8) rather than repeated here.

- **Make `plan()` a `CompositionGraph` method.** Rejected: would grow
  `CompositionGraph`'s public surface for every future consumer of
  graph data, rather than keeping consumers as independent free
  functions the way `snapshot()` already does for `ArchitectureSnapshot`.
  See "Why `plan()` is a free function" above.
- **Have `plan()` re-validate acyclicity/referential integrity
  independently.** Rejected: `CompositionGraph.__post_init__` already
  guarantees both at construction time (ADR-016); re-checking would
  duplicate validation logic this project has consistently kept in a
  single place at each layer (`is_compatible()` →
  `check_connection()` → `Connection` → `CompositionGraph`, each
  trusting the layer below rather than re-verifying it).
- **Use `networkx.topological_sort()` or another graph library.**
  Rejected: zero new dependencies is an established, hard constraint
  (R1/R11); Kahn's algorithm at the same scale `CompositionGraph`
  already handles (hundreds to low thousands of nodes for any
  realistic RAG composition) needs no library, and reusing the same
  algorithmic shape as ADR-016's cycle detection keeps the codebase's
  graph-traversal code consistent.
- **Tie-break simultaneously-ready nodes lexicographically by
  `node_id`.** Rejected: `CompositionGraph` already establishes and
  guarantees a deterministic node ordering (`graph.nodes`, ADR-016);
  introducing a second, different ordering concept (lexicographic)
  purely for tie-breaking would mean two independently-constructed
  graphs with nodes added in a different order, but compared equal
  under `CompositionGraph`'s own equality, could still be indifferent
  to which specific string sorts first — reusing the graph's existing
  declared order is simpler and matches what a caller who built the
  graph in a specific order would expect.
- **Store transitive dependencies on `ExecutionStep`, not just direct
  ones.** Rejected: transitive dependencies are a derived quantity a
  consumer can compute by walking `steps`; storing both direct and
  transitive sets on every step risks the two falling out of sync and
  roughly doubles the data for no consumer this step has identified a
  need for yet.

## Security

`plan()` reads only `GraphNode.id` and `Connection.source_node_id`/
`target_node_id` — the same minimal-surface fields `CompositionGraph`
itself already validates. No `component.__call__` is ever invoked —
verified by a dedicated test using a component whose `__call__` raises
`AssertionError` if invoked, proving planning succeeds without
triggering it. `ExecutionStep`/`ExecutionPlan` contain no `Component`
instances, so no provider client, credential, or open resource can
reach a plan, a log statement about a plan, or a future serialized
plan — by construction, not by redaction after the fact.

## Dependency review

Zero new runtime dependencies. `execution_plan.py` imports
`ragtorch.core.composition` (`CompositionGraph`) and the standard
library `dataclasses` — no `networkx`, no scheduler/workflow package,
no serialization framework.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `ExecutionEngine`,
`ExecutionContext`, `ArchitectureSnapshot`, `validate_snapshot()`,
`InputPort`, `OutputPort`, `is_compatible()`, `check_connection()`,
`Connection`, `CompositionGraph`, or `GraphNode` themselves.
`ExecutionPlan`/`ExecutionStep`/`plan()` are a pure addition, in a new
module. `Sequential` in particular is unaffected: it continues to
execute in constructor-registration order via its own loop, with no
dependency on `CompositionGraph` or `ExecutionPlan`.

## Testing strategy

Organized around the twelve invariants (E1-E12) established during the
Step 13 design audit:

- **E1 (every planned node exists in the source graph)** and **E5
  (every graph node appears exactly once)**: construction from a
  linear graph, a branching graph, a merging (diamond) graph, and a
  disconnected two-component graph, each asserting `steps` contains
  exactly the graph's node ids, no more, no fewer, no duplicates.
- **E2/E3 (dependencies reference real graph nodes/edges; the planner
  invents no dependency)**: for a graph with only `A→B, B→C` (not
  `A→C` directly), `C`'s step depends on `B` only, not on `A` —
  proving `plan()` does not add a transitive edge that does not exist
  as a direct `Connection`.
- **E4 (every dependency precedes its dependent)**: for every step in
  `plan.steps`, every id in its `dependencies` appears at an earlier
  index — checked generically across every constructed test graph, not
  only asserted for one hand-picked case.
- **E6 (deterministic output)**: the same `CompositionGraph`, planned
  twice independently, produces `==`-equal `ExecutionPlan`s; two
  independently-constructed but value-equal graphs (built via different
  code paths) also produce equal plans.
- **E7 (planning does not execute components)**: a component whose
  `__call__` raises `AssertionError` if invoked still participates in
  `plan()` without triggering it.
- **E8 (planning does not mutate the graph)**: the source
  `CompositionGraph`'s `nodes`/`connections` are identical before and
  after calling `plan()`.
- **E9 (no provider dependency)**: AST-based import check on
  `execution_plan.py`, reusing the established pattern.
- **E10 (disconnected DAGs are supported)**: a graph with two
  unconnected linear chains (`A→B` and `C→D`) plans successfully, with
  both chains' internal orderings respected.
- **E11 (multiple ready nodes are deterministically ordered)**: a
  diamond graph (`A→B, A→C, B→D, C→D`, i.e. both `B` and `C` become
  ready at the same point) plans the same way every time, and in
  `graph.nodes`' declared order among the tied candidates — a
  dedicated test constructs the same diamond shape with `B`/`C` added
  to the graph in the opposite declared order and confirms the tie
  break follows that order, not id sort or any other implicit rule.
- **E12 (empty graph behavior)**: `plan(CompositionGraph(nodes=(),
  connections=()))` returns `ExecutionPlan(steps=())`, no exception.
- Immutability: `ExecutionStep`/`ExecutionPlan` attribute assignment
  raises (frozen dataclasses).
- **13A/B (plan and step value equality)**: two independent `plan()`
  calls on the same graph produce `==`-equal `ExecutionPlan`s (subsumed
  by E6 above, but asserted directly via `==` rather than only via
  field-by-field comparison); a plan with one differing step (e.g.
  different `dependencies` order) is *not* `==` to the original —
  proving equality is not vacuously true.
- **13A/A (`dependencies` internal ordering is deterministic)**: a node
  with two predecessors (`D` depending on both `B` and `C`) produces
  the same `dependencies` tuple order across repeated `plan()` calls on
  the same graph, and the order matches the graph's own `connections`
  order — not merely "some consistent order," but specifically the
  graph-derived one.
- **13A/D (plan does not retain the graph)**: `ExecutionPlan` has no
  `graph` attribute — a structural test asserts `hasattr(plan, "graph")
  is False` (or the dataclass-fields equivalent), guarding against a
  future accidental addition reopening this decision silently.
- **13A/E (snapshot semantics under later graph mutation)**: construct
  `graph1`, compute `plan1 = plan(graph1)`, derive `graph2 =
  graph1.add_node(...)`, and assert `plan1` is unchanged (still equal
  to a freshly-recomputed `plan(graph1)`) after `graph2` is built —
  proving the plan is insulated from later graph evolution, not merely
  assumed to be from general immutability reasoning.
- Integration: a realistic Retriever→Reranker→Generator
  `CompositionGraph` (mirroring Step 11/12's fixtures) plans to
  `[retriever, reranker, generator]`; a fan-out graph (Retriever
  feeding both Reranker and Evaluator) plans with both downstream
  steps depending only on Retriever.

## Benchmark strategy

Per ADR-009, `benchmarks/step13_execution_plan.py`. Measures `plan()`
at 10/100/1,000/10,000 nodes across three shapes — a linear chain, a
"wide" graph (one root fanning out to N-1 independent leaves), and a
branching/diamond-heavy graph — as informational scaling evidence,
continuing directly from the lesson recorded in ADR-016/Step 12's own
evaluation: correctness proven only at a small hand-built scale is not
evidence of correctness at realistic scale, and Kahn's-algorithm-shaped
code in this codebase has already had one real bug (recursive
depth) caught specifically by benchmarking at 1,000 nodes. No hard
threshold asserted, consistent with prior benchmarks' methodology.

## Consequences

- A future executor (synchronous first, async/parallel later) has a
  ready-made, already-tested, deterministic dependency ordering to
  consume, without needing to invent topological sorting itself or
  re-derive it from `CompositionGraph.connections` on every run.
- The three-layer separation the Step 13 audit established —
  `CompositionGraph` (structural validity) / `ExecutionPlan`
  (deterministic ordering) / `ExecutionEngine` (runtime execution and
  observability) — is now concretely realized as three independent
  types with a one-way dependency direction, matching this project's
  consistent pattern of proving one primitive before building the next
  layer on top of it.
- Scope stays deliberately narrow: no executor, no parallelism, no
  async, no serialization, no new per-step metadata beyond
  `node_id`/`dependencies` — consistent with every prior step's
  discipline, and explicitly informed by the 18-question audit that
  preceded this ADR rather than jumping directly to an implementation.
