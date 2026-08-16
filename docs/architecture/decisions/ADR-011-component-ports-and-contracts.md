# ADR-011: Component Ports and Compatibility Contracts

## Status

Accepted

Verified via GitHub Actions (PR #3, run 31918774186): 179/179 tests
passing on Python 3.10, 3.11, and 3.12. The first push to this PR
failed on all three versions due to a real cross-version bug
(`isinstance(list[X], type)` differs between Python 3.10 and 3.12) that
local testing on a single 3.12 environment could not have caught — see
`evaluation/step7-evaluation.md` for the full account. Fixed and
re-verified against real 3.10/3.12 interpreters and, definitively, real
CI before this status was changed from Proposed.

## Context

`Component` (ADR-010) establishes that a component has a name, a type
descriptor, and a callable execution interface —
`__call__(input: InputT, *, context=None) -> OutputT`. `InputT`/`OutputT`
give us a *static* (mypy-time) type contract via Python generics, but
nothing in the framework can answer, at architecture-construction time
and without executing anything:

> Can the output of component A legally feed component B's input?

Today the only way to find out is to run the pipeline and see whether it
raises. Once real components exist (`Retriever` producing
`list[Document]`, a `Reranker` consuming `list[Document]`, a future
`GraphRetriever` producing something else entirely), a framework user
composing an architecture has no way to catch a wrong connection before
runtime — and the framework itself has no way to reason about
composition (which is the prerequisite for `Block`/`Architecture`,
per `docs/architecture/v0.1-architecture.md` §4).

## Problem

We need a way to describe a component's input/output boundary as
inspectable architecture metadata — separate from, but not duplicating,
the type information already expressed in `Component[InputT, OutputT]`'s
generic parameters and in `__call__`'s own annotations.

## Decision

Introduce two small, frozen dataclasses in `src/ragtorch/core/ports.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from ragtorch.core.errors import ValidationError


@dataclass(frozen=True)
class InputPort:
    name: str
    type: type

    def __post_init__(self) -> None:
        if not isinstance(self.type, type):
            raise ValidationError(
                f"InputPort '{self.name}' requires a Python class as type, got {self.type!r}."
            )


@dataclass(frozen=True)
class OutputPort:
    name: str
    type: type

    def __post_init__(self) -> None:
        if not isinstance(self.type, type):
            raise ValidationError(
                f"OutputPort '{self.name}' requires a Python class as type, got {self.type!r}."
            )
```

And one function:

```python
def is_compatible(output: OutputPort, input: InputPort) -> bool:
    """Return whether an output port can feed an input port.

    issubclass(T, T) is True, so this single check implements both
    exact-match and subtype compatibility. See Compatibility Rules
    below for what is deliberately NOT supported yet.
    """
    return issubclass(output.type, input.type)
```

`Port` instances are **architecture metadata, constructed explicitly by
whoever describes a component's boundary** — not derived automatically
from `__call__`'s runtime annotations via reflection (see Type
Representation and Security below), and not attached to `Component`
itself (see Non-goals). Nothing about `Component`'s existing three
members changes.

### Amendment: port type validity is enforced at construction, not at compatibility-check time

A first draft of this ADR left `type: type` unvalidated, which would let
`InputPort(name="x", type="Document")` construct successfully and then
raise an unrelated `TypeError` inside `issubclass()` the first time
`is_compatible()` ran — a deferred, confusing failure far from its
cause. Corrected per Staff review: `__post_init__` on both dataclasses
enforces `isinstance(self.type, type)` — the port's `type` field must be
an actual Python class object — and raises the existing
`ValidationError` immediately at construction if it isn't. This gives a
clean separation of responsibilities: **construction** is where invalid
port metadata is rejected (deterministically, at the point of the
mistake); **`is_compatible()`** is where two already-valid ports are
compared, and for valid inputs it always returns `bool`, never raises.
`list[Document]`, `Sequence[Document]`, `Any`, `Union[...]`, and
`Optional[...]` are therefore correctly rejected by construction (none
of `list[Document]` etc. is `isinstance(x, type)` — they are generic
alias objects, not classes) rather than silently accepted and failing
later — consistent with Compatibility Rules' scope (exact/subtype only)
below.

### Why dataclasses, not a schema/validation library

Matches the project's existing pattern (`RAGConfig`, ADR unnamed but see
`config.py`): frozen `@dataclass` for structured data, standard library
only. `Port` needs exactly two fields and one comparison; introducing
`pydantic`, `jsonschema`, `attrs`, or `typing-inspect` for that would
violate ADR-005-adjacent dependency discipline (this project's core has
had zero third-party runtime dependencies since Step 1) for no
capability we don't already have with a dataclass and `issubclass()`.

### Type representation: real Python types, never strings

`type: type` (or, in a future revision, `type: type | GenericAlias` if
`list[Document]`-style generics are needed — deferred, see Non-goals)
holds the actual runtime type object, not `"Document"` or
`"list[Document]"` as a string. A string-typed representation would
create a second, parallel type system the framework would need to keep
in sync with Python's own — string names collide across modules
(`retrieval.Document` vs `vision.Document`, both `"Document"`), can't be
`isinstance`/`issubclass`-checked without an `eval()`-equivalent lookup
step, and reintroduces exactly the "descriptive, not authoritative"
problem ADR-010 already named for `component_type`.

### Ports are not automatically derived from `__call__`'s annotations

This is a deliberate, security-motivated design choice (see Security
below). `typing.get_type_hints()` — the standard way to read a
callable's annotations when `from __future__ import annotations` is in
effect (used throughout this codebase) — evaluates string annotations
via the function's `__globals__` namespace, which is a real code-execution
surface for a hostile or merely careless third-party component: a
malicious forward-reference string (e.g. one crafted to reference an
attacker-controlled name resolved at import time) executes during
introspection, not during normal execution. `Port` construction is
therefore explicit: a component author (or, eventually, a small
decorator/registration helper — future work, not this ADR) states its
ports directly, e.g.:

```python
retriever_output = OutputPort(name="documents", type=list)
```

rather than the framework silently reflecting into `__call__` to guess.

### Compatibility rules: conservative on purpose

`is_compatible()` is exactly `issubclass(output.type, input.type)`,
which covers two cases in one check:

- **Exact match**: `issubclass(T, T)` is always `True`.
- **Subtype match**: a `DenseDocument` output can feed a `Document`
  input.

Deliberately **not** supported in this ADR: generic parameter matching
(`list[Document]` vs `Sequence[Document]`), `Union`/`Optional` inputs,
structural/duck-typed compatibility, or variance rules beyond
`issubclass`. Building a general-purpose type checker is a large,
open-ended project (mypy itself is that project); RAG-MODULE does not
need one to answer "can A feed B" for the components that exist today
(none) or the first ones that will exist (`Retriever`, `Reranker`,
`Generator` — all single concrete-type boundaries). Expanding
`is_compatible()`'s rules is additive and should wait for a real
component demonstrating the need, per this project's standing rule
("don't build architecture for hypothetical requirements").

### Error behavior: reuse `ValidationError`, add nothing new

`ragtorch.core.errors.ValidationError` already exists — "Raised when
input/output validation fails" — and is exactly the boundary both port
failure modes cross. No new exception type is introduced. Two distinct
points, two distinct meanings:

- **Construction** (`InputPort.__post_init__`/`OutputPort.__post_init__`):
  raises `ValidationError` immediately if `type` isn't a real Python
  class — an invalid *port definition*, caught at the point of the
  mistake, not deferred to whenever compatibility happens to be checked.
- **`is_compatible()`**: takes two already-valid ports and returns
  `bool` — `True`/`False`, never raises, for any pair of validly-
  constructed ports. A future compatibility-*enforcing* call site
  (e.g. a `Block`/graph builder in a later step) is responsible for
  raising `ValidationError` with a message identifying the two ports
  and their types when `is_compatible()` returns `False` — that
  enforcement point is not added by this ADR; see Non-goals.

### Performance: ports are inert unless constructed or compared

`InputPort`/`OutputPort` are plain dataclasses; `is_compatible()` is a
type check with no reflection over live objects. Nothing in this ADR
touches `Module.__call__`, `ExecutionEngine.execute`, or `Sequential`.
A component with no declared ports pays zero cost — port
construction/comparison happens only where an author or a future
composition layer explicitly does it, consistent with ADR-010's
"conformance checks are not a hot-path operation" rule extended to
ports.

## Non-goals

Explicitly deferred, not part of this decision:

- Attaching `input_ports`/`output_ports` to the `Component` protocol
  itself. `Component` stays exactly as ADR-010 defined it
  (`name`, `component_type`, `__call__`); ports are a separate,
  optional concept components may be described with, not a new required
  member. Whether/how `Component` eventually gains a ports property is
  future work once real components exist to inform the decision.
- A graph/`Block` builder that uses `is_compatible()` to validate an
  actual composed architecture (`docs/architecture/v0.1-architecture.md`
  §2 "Blocks", §4 "Composition model"). This ADR provides the
  compatibility primitive; wiring it into composition is a later step.
- Generic-parameter-aware compatibility (`list[X]` vs `Sequence[X]`),
  `Union`/structural typing, or any general type-theory beyond
  `issubclass`.
- Reflection-based port derivation from `__call__` annotations —
  rejected here on security grounds, not merely deferred; could be
  revisited only with an explicit sandboxing/allowlist design.
- Serialization of ports (JSON Schema, OpenAPI-style contracts).
- Async/streaming port variants.
- A component/port registry.

## Alternatives considered

- **String-based type names** (`OutputPort(name="documents",
  type="list[Document]")`). Rejected: creates a second type system
  requiring manual synchronization with Python's actual types; see
  Type representation above.
- **Automatic port derivation via `typing.get_type_hints()` on
  `__call__`.** Rejected: real code-execution surface via string
  annotation evaluation for a framework designed to run untrusted or
  loosely-vetted third-party components; see Security below.
  Convenience does not outweigh the risk for a framework whose stated
  security posture (ADR-003, ADR-010) has consistently chosen the
  conservative option.
- **Full structural/generic type compatibility (mypy-equivalent)
  now.** Rejected: large, open-ended scope with no current component to
  validate the design against — exactly the "don't build for
  hypothetical requirements" trap. Start conservative
  (exact-match + `issubclass`), expand only with evidence.
- **A `pydantic`-based `Port` model.** Rejected: first third-party
  runtime dependency the core would ever acquire, for a two-field
  dataclass's worth of capability. See Dependency review (in the
  companion implementation PR, not duplicated here).

## Compatibility

No changes to `Component`, `Module`, `ExecutionEngine`,
`ExecutionContext`, `Sequential`, or any existing error type. `ports.py`
is a wholly new, standalone module; nothing existing imports it yet, so
nothing existing can be affected by its addition. All 159 existing tests
(148 Steps 1-4 + 11 Step 6 Component contract tests) are expected to
pass completely unmodified.

## Security

- **No arbitrary code execution.** `Port` construction takes a `type`
  object directly (passed by the caller, who already has it in scope,
  e.g. `OutputPort(name="documents", type=Document)`); nothing in this
  design parses, `eval()`s, or reflects over strings or annotations at
  construction or compatibility-check time.
- **Annotations are not evaluated.** This ADR explicitly rejects
  `typing.get_type_hints()`-based derivation for the reason above —
  ports are always constructed with a real type object the caller
  already possesses.
- **No serialized schemas** are introduced or consumed.
- **`issubclass()` itself is safe** for concrete classes (no metaclass
  trickery is assumed or required by `is_compatible()`); if a future
  revision needs to handle exotic metaclasses safely, that is scoped to
  whatever change introduces the need.

## Dependency review

Zero new dependencies. `ports.py` imports only `dataclasses` (stdlib).

## Testing strategy

- **Port construction — valid**: `InputPort`/`OutputPort` construct
  correctly for a real class; fields are immutable (frozen dataclass —
  attempting assignment raises).
- **Port construction — invalid**: a non-class `type` value (a string,
  an int, a generic alias like `list[Document]`) raises `ValidationError`
  immediately at construction, not deferred to `is_compatible()`.
- **Compatibility — exact match**: `is_compatible()` returns `True` for
  identical types.
- **Compatibility — subtype match**: `is_compatible()` returns `True`
  when the output type is a subclass of the input type.
- **Incompatibility**: `is_compatible()` returns `False` for unrelated
  types, and for a *supertype* output feeding a *subtype* input (the
  relationship must not be accidentally symmetric).
- **No accidental permissiveness**: `is_compatible()` must not treat
  `Any`, `object`, or an unrelated type as universally compatible unless
  the input port's declared type is actually `object` (in which case
  `issubclass(x, object)` is trivially, correctly `True` for any class —
  documented as expected Python behavior, not a special case).
- **Integration**: a `FakeProducer` (`OutputPort(name="value",
  type=int)`) and `FakeConsumer` (`InputPort(name="value", type=int)`)
  connect successfully; a mismatched pair (`str` output into `int`
  input) is correctly reported incompatible — proven without any LLM,
  database, network, or provider dependency.
- **Provider independence**: `ports.py`'s own imports contain no
  provider/vendor reference (verified by inspection, matching ADR-005's
  standing rule).

## Benchmark strategy

Per ADR-009, `benchmarks/step7_component_ports.py`. Measures: `Port`
construction, `is_compatible()` evaluation, and — critically — a
`Module`/`Component` call *with no ports involved*, to confirm (as
Decision/Performance already argues by design, but should be measured,
not assumed) that a component author who never touches `ports.py` pays
literally zero cost, since nothing in the hot `__call__` path references
it. Compared against the Step 6 baseline (`Module(input)` 1.9µs p50,
`Sequential(10)` ~20.5µs p50) as fixed reference data.

## Future extension points

This design is deliberately positioned so the following remain additive:

- Generic-parameter-aware compatibility, once a real component
  (e.g. a retriever returning `list[Document]` feeding a reranker
  accepting `Sequence[Document]`) demonstrates exact-match/`issubclass`
  is insufficient.
- `Component` gaining an optional `input_ports`/`output_ports` property
  (or a separate `PortDescribable` protocol), once real components exist
  to prove the right shape — mirroring ADR-010's own deferral of
  `capabilities`/`configuration` for the same reason.
- A `Block`/graph composition layer that calls `is_compatible()` to
  validate an architecture before execution — the actual payoff this
  ADR exists to enable, scoped to a future step.
- A `ValidationError`-raising enforcement point at whatever composition
  boundary is introduced, using the existing error type rather than a
  new one.

## Consequences

- The framework gains a way to describe and check component boundary
  compatibility as inspectable metadata, without executing anything and
  without a second type-system-in-strings.
- `Component` remains exactly as small as ADR-010 left it — ports are
  additive, optional, external metadata, not a growth of the core
  contract.
- The conservative compatibility relation (exact + subtype only) is a
  known, documented limitation, not an oversight — expanding it has a
  named trigger condition (a real component that needs it) rather than
  being spec'd speculatively now.
- No component author is forced to declare ports to use `Component`;
  `ports.py` is opt-in infrastructure a future `Block`/graph layer will
  consume, not a requirement Step 7 imposes on Step 6's contract.
