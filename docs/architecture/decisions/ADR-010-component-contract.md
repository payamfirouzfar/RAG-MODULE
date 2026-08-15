# ADR-010: Component as the Stable Conceptual Unit

## Status

Accepted

Verified via GitHub Actions (PR #2, run 31915309706): 159/159 tests
passing on Python 3.10, 3.11, and 3.12; ruff check/format, mypy, and
package build all green on real CI infrastructure, not local checks
alone. See `evaluation/step6-evaluation.md` for the full verification
ladder.

## Context

`Module` (ADR-001) currently provides the framework's execution and
composition mechanisms: identity via `_name`, child registration,
`forward`/`__call__`, `ExecutionContext` propagation (ADR-007),
`ExecutionError` wrapping, and inspection. It is, and remains, the
concrete implementation primitive everything in `ragtorch.core` is built
on.

But `Module` is an *implementation* abstraction — it carries registration
machinery, an `__init__` contract, and inheritance-based reuse. The
framework's future direction (`docs/architecture/v0.1-architecture.md`)
calls for RAG components — `Retriever`, `Generator`, `Embedder`,
`Reranker`, and others not yet designed — to be usable by the framework
without being forced to inherit from `Module` or depend on any
provider-specific base class. A third-party author should be able to
write a component that RAG-MODULE recognizes and executes without
importing `ragtorch.core.Module` at all.

Nothing in the repository today expresses that boundary as a stable,
minimal, checkable contract — only as the shape `Module` already happens
to have.

## Decision

Introduce a minimal structural `Component` protocol
(`src/ragtorch/core/component.py`) as the stable conceptual contract for
executable RAG components. The protocol has exactly three members:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from ragtorch.core.context import ExecutionContext

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@runtime_checkable
class Component(Protocol[InputT, OutputT]):
    @property
    def name(self) -> str: ...

    @property
    def component_type(self) -> str: ...

    def __call__(self, input: InputT, *, context: ExecutionContext | None = None) -> OutputT: ...
```

Nothing else is added. No `capabilities`, no `configuration`, no
lifecycle methods, no async/streaming variants — see Non-goals.

### Why `Protocol`, not `ABC` or a `Component` base class

`Protocol` gives us structural typing: a class satisfies `Component`
by having the right shape, not by inheriting from it. This is the
entire point. With an `ABC` or a concrete base class, every future
component author would need:

```python
class MyRetriever(Component): ...
```

creating a hard dependency on `ragtorch.core` and a single-inheritance
slot every implementation spends on us. With a structural `Protocol`, a
plugin author writes:

```python
class MyRetriever: ...  # has name, component_type, __call__
```

with no import of `ragtorch` at all beyond whatever they choose to
type-check against, and RAG-MODULE still recognizes it:
`isinstance(MyRetriever(), Component)` is `True` because
`@runtime_checkable` makes that check structural, not nominal. This is
consistent with the precedent already set by `ragtorch.evaluation.Metric`
(ADR-004), the only other `@runtime_checkable Protocol` in the codebase.

### Module compatibility

`Module` is not rewritten, not re-parented, and does not gain a new
inheritance relationship. Two properties are added to the existing
class:

```python
@property
def name(self) -> str:
    return self._name


@property
def component_type(self) -> str:
    return type(self).__name__
```

`_name` is unchanged; the constructor is unchanged; every existing
`Module` subclass, including every one already in the test suite,
structurally satisfies `Component` the moment these two properties
exist — with zero migration and zero call-site changes anywhere in the
repository.

### `component_type` is descriptive identity, not a serialization identifier

Identity descriptors (`name`, `component_type`) are deterministic and
inspectable. They are not yet guaranteed as long-term serialization
identifiers; a dedicated stable type identifier may be introduced by a
future architecture decision.

For this step, `component_type = type(self).__name__` is acceptable and
sufficient: it answers "what kind of thing is this" for humans and for
`inspect()`-style tooling. `type(self).__name__` will collide across
modules (`retrieval.DenseRetriever` and `vision.DenseRetriever` both
report `"DenseRetriever"`), is not versioned, and is not stable across a
class rename. A future serialization design (registered identifiers,
fully-qualified paths, or an explicit alias table) is deferred until
serialization itself is designed — promising stability here before that
design exists would constrain it before we have evidence of what it
needs.

### Identity: `(name, component_type)`, never a class name alone

`name` is the instance-level, human-assigned label (`Module._name`,
currently defaulting to the class name but freely reassignable by
whoever constructs it — unchanged by this ADR); `component_type` is the
type-level label. Two components of the same `component_type` with
different `name`s are different components; this is why identity is
never `type(self).__name__` alone. This mirrors the distinction ADR-002
already draws between `Module` (what computes) and `Run`
(one execution of it) — extended one level: `Component` identity
(what kind of thing, which instance) is a third, separate concept from
execution identity (`ExecutionContext.run_id`, which execution).
`Component` does not introduce a runtime/execution identity field of its
own; `ExecutionContext` remains the only place that lives.

### Context remains explicit; no new context mechanism

`Component.__call__`'s `context` parameter is the same optional,
keyword-only `ExecutionContext | None` that `Module.__call__` already
has (ADR-007). `Component` does not add a second context system, a
default value derived from global state, or any implicit propagation.
A component that doesn't care about context (`Module`'s existing
signature-detection behavior, unchanged by this ADR) works identically
whether accessed as a `Module` or through the `Component` protocol —
they are the same object.

### `Component` conformance checks are not a hot-path operation

`isinstance(obj, Component)` on a `@runtime_checkable` `Protocol` has
real cost (it inspects the object's attributes at each call). This ADR
establishes, as a hard rule and not merely a style preference: no
production code path — `Module.__call__`, `ExecutionEngine.execute`,
`Sequential.forward`, or any future equivalent — performs a `Component`
conformance check on every invocation. Conformance checking belongs at
explicit boundaries: registration, tests, and developer tooling, where
it runs once per component instance, not once per call.

## Non-goals

Explicitly deferred, not part of this decision:

- `capabilities` (e.g. `frozenset[str]` declaring sync/async/streaming
  support) and `configuration` (typed, validated component settings).
  Both were considered for this contract and deliberately excluded —
  see Alternatives considered.
- Async execution, streaming execution. The contract must not *prevent*
  either being added later (see Consequences), but neither is designed
  or implemented here.
- Serialization of a `Component`'s identity or configuration.
- `Block` / composite-component and `Architecture` / graph abstractions
  (see `docs/architecture/v0.1-architecture.md` §2-4) — `Component` is
  the foundation those will be built on, not a first attempt at them.
- A component registry, plugin discovery mechanism, or provider routing.
- Any change to `ExecutionEngine`, `ExecutionContext`, `Sequential`, or
  the event/error system beyond the two new `Module` properties above.
- Renaming the `ragtorch` package.

## Alternatives considered

- **Include `capabilities: frozenset[str]` and `configuration:
  Mapping[str, Any]` in the Step 6 contract**, matching an earlier,
  broader sketch of `Component` circulated before this ADR. Rejected:
  neither has a real implementation to validate its shape against yet
  (no `Retriever`, no `Generator` exists), and ADR-001's own principle
  ("the interface should be small... difficult to misunderstand")
  argues against committing to fields nothing yet needs. Both remain
  natural, additive extensions once a real component exists to prove
  what shape `configuration` should take.
- **`ABC` with concrete default methods.** Rejected: forces inheritance,
  the exact coupling structural typing exists to avoid; see Decision.
- **Give `Module` a synthetic runtime/serialization identity (e.g. a
  UUID or fully-qualified module path) now.** Rejected: no serialization
  design exists yet to consume it, and inventing an identity scheme
  speculatively risks designing it wrong before real requirements exist
  — the same reasoning ADR-006 used to defer `RunArtifact` persistence.
- **Make `Component` conformance a runtime guard inside
  `ExecutionEngine.execute` or `Module.__call__`.** Rejected as a hot-path
  operation — see the dedicated rule in Decision. `Component` is a
  contract for humans and tooling to depend on, not a runtime gate
  every call pays for.

## Compatibility

No existing public API changes. `Module.__call__`'s signature, `forward`
signature-detection behavior, event emission, error wrapping (both the
context and no-context paths added in ADR-007/ADR-008), and inspection
methods are untouched. Every existing `Module` subclass gains two new
properties (`name`, `component_type`) it did not have before; nothing
that previously worked can now fail, because nothing existing calls
these properties or depends on their absence.

## Testing strategy

Contract tests (not merely unit tests of `Module`) must prove structural
typing actually works, not just that `Module` happens to satisfy it:

- An existing concrete `Module` satisfies `Component`.
- `Module.name` and `Module.component_type` return the expected values.
- An **independent, non-`Module`-inheriting** class implementing `name`,
  `component_type`, and `__call__` also satisfies `Component` —
  proving the protocol is structural, not accidentally testing only
  `Module`.
- A **deliberately incomplete** class (missing one required member)
  does **not** satisfy `Component` — proving the protocol isn't
  accidentally permissive.
- Explicit-context and no-context invocation both work through a
  `Component`-typed reference, with existing `ExecutionContext`
  propagation and `ExecutionError` semantics unchanged.
- All 148 pre-existing tests continue passing unmodified.

## Benchmark strategy

Per ADR-009, the Step 6 benchmark lives at
`benchmarks/step6_component_overhead.py`. It measures the existing hot
paths (`Module.__call__`, `Sequential`, `inspect()`) before/after this
change to confirm the two new properties add no meaningful per-call cost
(they are not on any hot path — see Decision), plus a separate,
explicitly-labeled measurement of `isinstance(x, Component)` itself,
so its real cost is documented rather than assumed cheap. The
pre-existing baseline (Module call 1.9µs p50, Sequential(10) 20.6µs p50,
inspect() 13.4µs p50, register_module 3.4µs p50) is treated as fixed
reference data, not re-run to seek a more favorable number.

## Future extension points

This contract is deliberately small so the following can be added later
**without breaking it**:

- `capabilities`/`configuration` as additional optional protocol
  members or a separate, composable protocol (e.g. `Configurable`).
- Async execution via a sibling protocol (e.g. `AsyncComponent`) rather
  than modifying `Component.__call__`.
- A registered, versioned `component_type` identifier once
  serialization is designed.
- `Block`/`Architecture` composition built on top of components that
  satisfy this same contract.

## Consequences

- Every future `Retriever`, `Generator`, `Embedder`, `Reranker` can
  implement `Component` — including as a plain class with no
  `ragtorch` import — without any change to `ragtorch.core`.
- `Module` keeps its existing, narrow responsibility (ADR-001) and
  simply gains a documented compatibility relationship to the new
  contract; no migration risk is introduced anywhere in the existing
  148 tests.
- `component_type`'s current meaning (descriptive, not a serialization
  identifier) is a real, documented constraint on future work: whoever
  designs serialization must explicitly decide whether/how to
  strengthen it, rather than discovering an accidental promise already
  made.
- The "no `Component` check in the hot path" rule is now a checkable
  architectural invariant, not an unwritten convention future
  contributors could violate without knowing they'd broken something.
