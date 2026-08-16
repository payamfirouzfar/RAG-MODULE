# ADR-014: Composition Preconditions

## Status

Proposed

## Context

Three independent primitives exist today with no connection between
them:

- `InputPort`/`OutputPort`/`is_compatible()` (ADR-011) describe a
  single component's boundary and check whether one output can feed
  one input — `issubclass(output.type, input.type)`, `True`/`False`.
- `ArchitectureSnapshot`/`snapshot()` (ADR-012) describe a `Module`
  tree's structure — nodes and containment, never data-flow.
- `validate_snapshot()` (ADR-013) checks that a snapshot is a
  well-formed, non-empty rooted tree — structure only, no ports
  involved.

`docs/architecture/requirements-matrix-v0.1.md`'s own "Next priority"
names the eventual destination: "a `Block`/graph composition layer that
uses `is_compatible()` (Ports), `ArchitectureSnapshot` (Step 8), and
`validate_snapshot()` (Step 9) together." `v0.1-architecture.md` §2
already commits to the term **Block** — "a reusable composition of
components... itself composable" — as the intended name for that
future layer, so this ADR does not invent new vocabulary.

**This ADR does not build that layer.** Step 10 establishes only the
missing **port-level composition precondition primitive** — a single
function checking whether one component's declared output can legally
feed another's declared input — that a future `Block`/composition
layer can use *alongside* `ArchitectureSnapshot` and
`validate_snapshot()`. It does not itself integrate those three
systems, does not touch `ArchitectureSnapshot`/`ArchitectureChild`, and
does not introduce a `Block` class or graph executor. Confirmed with
the project owner before drafting: building an actual composite type
is a later step, once this narrower primitive exists to build it on —
matching the project's consistent pattern of one self-contained
primitive per step (Steps 6-9 each did exactly this). The dependency
chain this ADR actually establishes:

```text
Step 7 (Ports)
  is_compatible()
        |
        v
Step 10 (this ADR)
  check_connection()
        |
        v
Future Block / Composition layer
        |
        +-- ArchitectureSnapshot  (Step 8, unmodified by this ADR)
        +-- validate_snapshot()  (Step 9, unmodified by this ADR)
```

`check_connection()` sits between Ports and a future composition
layer; it does not sit between Ports and Snapshot/Validation, which
remain independent of it until a future step deliberately connects
them.

## Problem

We need a way to ask, before two components are wired together in any
future composition: "can this component's declared output actually
feed that component's declared input?" — with a **raising** contract
(unlike `is_compatible()`'s `bool` return), because a composition
precondition failure should behave like every other structural failure
in this codebase (`validate_snapshot()`, `Port.__post_init__`): fail
loud, with a specific message, not require the caller to remember to
check a boolean.

## Decision

### Public contract

```python
def check_connection(output: OutputPort, input: InputPort) -> None:
    """Raise ValidationError if output cannot feed input.
    Returns None if the connection is valid.
    """
```

Deliberately the thinnest possible layer over the existing
`is_compatible()`:

```python
def check_connection(output: OutputPort, input: InputPort) -> None:
    if not is_compatible(output, input):
        raise ValidationError(
            f"Cannot connect output {output.name!r} ({output.type.__name__}) "
            f"to input {input.name!r} ({input.type.__name__}): incompatible types."
        )
```

### Why a raising wrapper, not just reusing `is_compatible()` directly

`is_compatible()` (ADR-011) is correctly a `bool`-returning predicate —
it answers a yes/no question with no implied consequence. A
*precondition* check has a different contract: the caller's intent is
"stop me if this is wrong," matching every other structural check in
this codebase (`validate_snapshot()`, `InputPort.__post_init__`,
`OutputPort.__post_init__` all raise `ValidationError`, none return
`bool`). Keeping `is_compatible()` unchanged (still `bool`, still
side-effect-free, per ADR-011) while adding a distinct raising
function preserves both call shapes for the two different use cases
they each actually serve — a caller who wants to build a compatibility
matrix or report multiple problems uses `is_compatible()`; a caller who
wants to gate composition on the first failure uses
`check_connection()`.

The two intentional APIs, side by side:

| API                  | Purpose | Result          |
| --------------------- | ------- | ---------------- |
| `is_compatible()`     | Ask     | `bool`             |
| `check_connection()`  | Enforce | `None` / raises       |

### `is_compatible()` is the single source of truth for compatibility semantics

`check_connection()`'s body is *exactly* `if not is_compatible(output,
input): raise ...` — it never re-implements or duplicates
`issubclass(output.type, input.type)` itself. This is deliberate, not
incidental: if `is_compatible()`'s compatibility rules are ever
extended (e.g. the generic-parameter-aware matching ADR-011 explicitly
deferred), `check_connection()` inherits the improvement automatically,
with no parallel logic to keep in sync. This is the concrete answer to
"can this be extended?" — the extension point is `is_compatible()`
alone; `check_connection()` is purely a wrapper around whatever that
function currently decides.

### `check_connection()` checks; it does not connect

Despite the name, `check_connection()` performs no action beyond
raising or not: it does not register, store, mutate, wire, or execute
a connection between the two components the ports belong to, and it
does not modify either `Port` object. It answers "would this proposed
connection be legal?" — the same relationship `is_compatible()` already
has to that question, just with a raising contract. A future `Block`
that actually *establishes* connections between components is
unaffected by this ADR and remains explicit future work (see
Non-goals).

### Argument contract: `OutputPort`/`InputPort` instances only

`check_connection()`, like `is_compatible()` before it, assumes its
arguments are actual `OutputPort`/`InputPort` instances and accesses
`output.type`/`input.type`/`output.name`/`input.name` directly. Passing
an object outside that contract (e.g. `None`, a plain object, a
malformed duck-typed stand-in) is **programmer misuse**, not a case
this version normalizes into a clean `ValidationError` — no runtime
`isinstance`/duck-type check is added defensively "just in case." This
is stated explicitly, not left to be assumed, because an unstated
contract invites a future caller to believe
`check_connection(None, None)` is guaranteed to raise
`ValidationError` specifically, when in fact it would raise whatever
`AttributeError` accessing `.type` on `None` happens to produce. If a
real need for defensive argument validation is demonstrated later, it
is a deliberate, separate addition — not implied by this ADR.

### Location: `src/ragtorch/core/ports.py`, not a new module

Unlike Steps 8/9 (which each introduced a new module for a genuinely
new concern), `check_connection()` is not a new concern — it is a
thin, same-concern wrapper over `is_compatible()`, which already lives
in `ports.py`. Introducing `composition.py` or `preconditions.py` for
an eight-line function would be premature module proliferation; a
`Block`/composition module remains a legitimate *future* addition once
there is an actual composite type to put in it (see Non-goals).

### No new exception type

`ValidationError` is reused, consistent with every prior step's
established convention for structural/architectural failures.

### No integration with `ArchitectureSnapshot`/`validate_snapshot()`

`check_connection()` operates purely on two `Port` objects; it does not
read or produce an `ArchitectureSnapshot`, and `validate_snapshot()` is
not changed to call it. `ArchitectureNode.input_ports`/`output_ports`
(ADR-012) remain empty-by-default with no discovery mechanism — this
ADR does not change that. Wiring `check_connection()` into snapshot
validation (e.g. "does every declared containment relationship also
have compatible ports") is deferred until nodes actually carry
non-empty ports in practice, which requires the currently-nonexistent
port-population mechanism ADR-012 explicitly deferred.

## Non-goals

Explicitly deferred, not part of this decision:

- **A `Block`/composite type.** No class holding an ordered or graph
  structure of components is introduced. `v0.1-architecture.md`'s
  "Block" remains a named future concept, not implemented here.
- **A graph/data-flow executor.** Nothing here executes components or
  determines execution order.
- **Automatic port discovery** from `Module`/`Component` attributes.
  Still rejected per ADR-011's original reasoning; `check_connection()`
  takes explicit `OutputPort`/`InputPort` arguments, same as
  `is_compatible()` already does.
- **Wiring `ArchitectureSnapshot` to carry data-flow edges.** Still an
  explicit ADR-012/013 non-goal; unchanged here.
- **Batch/multi-connection checking** (e.g. "validate every edge in a
  proposed graph at once"). `check_connection()` checks exactly one
  proposed connection; a caller checking many calls it in a loop. If a
  batch API is later needed, it is additive.
- **Generic-parameter-aware or structural compatibility.** Still
  bounded by `is_compatible()`'s own scope (ADR-011): exact-match and
  `issubclass` only.

## Alternatives considered

- **Extend `is_compatible()` itself to optionally raise** (e.g. a
  `strict: bool = False` parameter). Rejected: overloads one function
  with two different contracts based on a flag, which is exactly the
  kind of API ambiguity this project's own conventions avoid elsewhere
  (compare `Run.succeed()`/`Run.fail()` as distinct methods rather than
  one method with a status flag). A second, clearly-named function is
  more explicit at every call site.
- **Introduce the `Block` type now, since the matrix already names it
  as the next priority.** Rejected for this step: per the scope
  decision above, no composite type exists yet to validate the right
  API shape against — building `check_connection()` first, and letting
  a `Block` consume it once justified, follows the same "prove the
  primitive before the composite" sequencing already used for
  `Component` → `Sequential`'s later features, and `Port`/`Snapshot`/
  `Validation` individually before anything connects them.
- **Put `check_connection()` in `architecture.py`.** Rejected: it does
  not operate on an `ArchitectureSnapshot` at all, only on two `Port`
  objects — `ports.py` is the correct home by subject matter, not
  `architecture.py`.

## Security

`check_connection()` reads only the two `Port` objects' `type`/`name`
fields (already-validated at construction per ADR-011) and calls the
existing `is_compatible()`. No new reflection, no execution, no
arbitrary object inspection — a strict subset of `is_compatible()`'s
already-minimal surface.

## Dependency review

Zero new dependencies. No new imports beyond what `ports.py` already
has (`ValidationError`; `is_compatible()` is already local to the same
module).

## Compatibility

No changes to `Component`, `Module`, `ExecutionEngine`,
`ExecutionContext`, `Sequential`, `inspection.py`, `architecture.py`,
or `is_compatible()`/`InputPort`/`OutputPort` themselves.
`check_connection()` is a pure addition to `ports.py`.

## Testing strategy

- Compatible ports: `check_connection()` returns `None`.
- Incompatible ports: raises `ValidationError` naming both port names
  and types.
- Subtype-compatible ports (mirroring `is_compatible()`'s own subtype
  test): returns `None`.
- Determinism: calling twice with the same inputs produces the same
  outcome.
- No side effects: neither `Port` object is mutated by `check_connection()`.
- No side effects on the existing API: an explicit regression test
  asserts `is_compatible(valid_output, valid_input) is True` and
  `is_compatible(invalid_output, invalid_input) is False` continue to
  hold unchanged — `check_connection()` is additive, not a
  modification, and this is proven, not merely implied by "we didn't
  edit that function."
- Integration: a realistic Retriever→Reranker→Generator port chain
  (mirroring the Step 7 integration test fixtures) — compatible pairs
  pass, the deliberately incompatible Retriever→Generator pair raises.

Explicitly **not** tested: behavior for arguments that are not
`OutputPort`/`InputPort` instances (e.g. `None`). Per the Argument
contract section above, no specific failure behavior is promised for
that case, so no test asserts one — adding such a test would encode an
API guarantee this ADR deliberately does not make.

## Benchmark strategy

Per ADR-009, `benchmarks/step10_composition_preconditions.py`.
Measures `check_connection()` for a compatible and an incompatible
pair, compared informally against Step 7's own `is_compatible()`
baseline (~0.1µs) — expected to be roughly the same order of magnitude,
since `check_connection()` adds only one conditional and, on the
failure path, one f-string construction. No hard threshold asserted,
consistent with prior benchmarks' methodology.

## Consequences

- A future `Block`/composition type has a ready-made, already-tested
  precondition primitive to call before connecting two components,
  rather than needing to invent one alongside the composite type
  itself.
- The distinction between "check" (`is_compatible`, `bool`) and
  "enforce" (`check_connection`, raises) is established once, as a
  reusable pattern, rather than each future composition feature
  deciding its own error-handling convention ad hoc.
- Scope stays deliberately narrow: no composite type, no graph, no
  executor — consistent with every prior step's discipline of proving
  one primitive before building on it.
