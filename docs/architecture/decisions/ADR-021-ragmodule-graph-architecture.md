# ADR-021: Graph-backed RAGModule Architecture

## Status

Accepted

Accepted after real GitHub Actions post-merge CI confirmed on the
actual merged `main` SHA — not from PR CI or local checks alone, per
this project's standing rule that "PR green is not proof." Evidence
trail:

- PR #22 (initial contract freeze + circular-import correction found
  during 17D): merged `e056b06`, post-merge CI run
  [31985560271](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31985560271),
  406/406 on 3.10/3.11/3.12.
- PR #23 (implementation): merged `419f643`, post-merge CI run
  [31992874525](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31992874525),
  431/431 on 3.10/3.11/3.12, lint clean, on commit `419f643`.

## Context

`RAGModule` was introduced in ADR-001 as a marker subclass of `Module`
identifying top-level RAG systems, with explicitly "no added behavior"
— confirmed by direct inspection of `module.py`: `class
RAGModule(Module): pass`-equivalent, with only a docstring. The only
existing test coverage (`test_module.py`) checks `issubclass`/
`isinstance`, never any behavior. The established, tested usage
pattern is subclassing with a hand-written `forward()`:
`class MyRAG(RAGModule): def forward(self, input): ...`.

Step 16 (ADR-020) introduced `Block`: a `Module` subclass owning a
`CompositionGraph`, delegating execution to the existing
`plan()`/`Executor`/`ExecutionEngine.execute_plan` chain, requiring
zero runtime changes. `docs/architecture/v0.1-architecture.md` §2
names `Architecture` as the layer directly above `Block`/`Graph`: "A
complete RAG design composed from components and blocks. Architectures
are user-defined and must not require changes to core." Requirement
A3 names the exact gap: *"Architectures are user-defined | RAGModule
marker exists | RAGModule semantics too weak."*

Grounded in direct inspection (17A/17B/17C audit) of `module.py`
(`RAGModule`, `Module.register_module`, `Module.__setattr__`,
`Module.snapshot`/`inspect`), `block.py`, `sequential.py`, and
`test_module.py` (full files, not assumed) — including two findings
that changed this ADR's design mid-draft before any code was written:

1. **Making `RAGModule` inherit `Block` would break the existing,
   tested subclass-and-override-`forward()` pattern** — `Block`'s
   constructor requires `graph`/`input_node`/`output_node` and its
   `forward()` is already concretely implemented, incompatible with
   `RAGModule`'s current zero-argument-constructor,
   override-`forward()` contract. Rejected before drafting a
   contract around it.
2. **A private adapter that both calls `self.register_module("block",
   block)` and assigns `self._block = block` double-registers the same
   child** — `Module.__setattr__` auto-registers any `Module`-valued
   attribute assignment (confirmed by direct inspection:
   `if isinstance(value, Module) and modules is not None:
   self.register_module(name, value)`). Verified by constructing the
   adapter and calling `.inspect()`: the child appeared twice under
   `"block"` and `"_block"` before this was caught and fixed to a
   single `self._block = block` assignment, mirroring how `Sequential`
   avoids the same trap (it calls `register_module` explicitly and
   never separately assigns the same value to an attribute).
3. **A third finding corrected an assumption in this ADR's own first
   draft**, not merely a Step-16 leftover: an initial version of this
   ADR asserted that `RAGModule.from_graph(...)`'s failure propagation
   must satisfy `exc_info.value is original_error` (single-hop
   `__cause__`). Direct construction proved this false — and, more
   importantly, proved it was never actually true anywhere multi-layer
   `Module` composition already exists. `Module.__call__` wraps every
   exception into a fresh `ExecutionError` at *every* layer it passes
   through (confirmed by reading `module.py`'s `__call__`); a
   `Block` nested inside a `Sequential` today, on already-merged
   `main`, already produces a two-layer `ExecutionError` chain
   (`Sequential`'s wrap around `Block`'s own wrap around the original
   exception) — verified by direct construction against `main`, not
   assumed. This was previously untested (Step 16's own
   `test_block_failure_propagates_through_sequential` only asserted
   `pytest.raises(ExecutionError)`, never identity or depth). This is
   `Module.__call__`'s correct, universal, existing convention, not a
   defect — a graph-backed `RAGModule` calling `self._block(input,
   context=context)` (through `Module.__call__`, exactly as
   `Sequential.forward` already calls its own children) is consistent
   with it, not an exception to it. The originally-drafted single-hop
   assertion is corrected below.

**This ADR does not change `RAGModule`'s existing class hierarchy,
constructor, or subclass contract, does not introduce a second
execution system, does not add plan caching, serialization, or async
execution, and does not support calling `from_graph` on an arbitrary
`RAGModule` subclass.** It answers: given a `CompositionGraph`, what
is the smallest additive `RAGModule` construction path that produces
an actual `RAGModule` instance (preserving `isinstance(x, RAGModule)`)
while delegating all execution to the existing, unmodified
`Block`/`plan()`/`Executor`/`ExecutionEngine.execute_plan` chain?

```text
                    Module
                      |
          +-----------+-----------+
          |                       |
     RAGModule                  Block
          |                       |
   (unchanged: subclass    owns CompositionGraph
    + override forward())         |
          |                 plan() -> ExecutionPlan
          |                       |
          |                    Executor
          |                       |
          |          ExecutionEngine.execute_plan()
          |                       |
          +---- from_graph() -----+
                     |
                     v
         _GraphBackedRAGModule(RAGModule)
                     |
                     +-- owns a Block (single registered child)
                     +-- forward() delegates to that Block via
                         Module.__call__, exactly as Sequential
                         already delegates to its own children
```

## Problem

We need a construction path that (a) lets a caller build a
graph-backed top-level architecture without hand-writing a `forward()`
method, (b) returns something that satisfies `isinstance(x, RAGModule)`
so ADR-001's existing marker semantics remain meaningful for
graph-backed architectures too, (c) does not change `RAGModule`'s
existing constructor or the still-fully-supported subclass pattern,
(d) introduces no second execution system — reusing `Block` internally
rather than reimplementing graph traversal, and (e) states the actual,
verified failure-propagation contract rather than an assumed one.

## Open questions this ADR must decide before any code is written

**Q1 — Does `RAGModule`'s class hierarchy change?** No.
`class RAGModule(Module):` is unchanged. Rejected: `class
RAGModule(Block)` — breaks the existing, tested
subclass-and-override-`forward()` pattern (`Block.__init__` requires
`graph`/`input_node`/`output_node`; `Block.forward` is already
concretely implemented). No existing test or documented usage is
touched by this ADR.

**Q2 — What is the graph-backed construction path?**
`RAGModule.from_graph(graph, *, input_node, output_node) -> RAGModule`,
a classmethod on `RAGModule` itself (available to `RAGModule` directly;
see Q3 for why it is not promised on arbitrary subclasses). Matches
`Block`'s own already-established `input_node`/`output_node` contract
exactly — no new entry/exit-node convention invented.

**Q3 — Does `from_graph` work on an arbitrary `RAGModule` subclass
(`MyRAG.from_graph(...)`)?** Not promised in this version. Rejected:
supporting arbitrary subclasses would require answering what a
subclass's own `__init__`/custom state/overridden `forward()` should
do when the factory is used instead of normal construction — no
real requirement has demonstrated a need for this, and answering it
speculatively would freeze API surface no evidence justifies yet. The
factory is documented as tied to `RAGModule` itself.

**Q4 — Does `from_graph` return a `Block` or a `RAGModule`?** A
`RAGModule` — specifically, a private `_GraphBackedRAGModule(RAGModule)`
instance wrapping a `Block`. Rejected: returning the `Block` directly
— would silently fail `isinstance(x, RAGModule)` for a caller relying
on ADR-001's existing top-level-system marker, breaking the semantic
meaning of "this is an architecture" for exactly the callers this ADR
is meant to serve.

**Q5 — Is the adapter public?** No — `_GraphBackedRAGModule` is
private, module-internal. The public contract is
`RAGModule.from_graph(...)`, not `_GraphBackedRAGModule(...)`. This
preserves freedom to change the internal implementation later (e.g. a
future richer `Architecture` type) without breaking callers who only
ever used the factory.

**Q6 — How does the adapter register/store its `Block`?** A single
`self._block = block` assignment — relying entirely on
`Module.__setattr__`'s existing auto-registration mechanism, the same
mechanism every other `Module` attribute assignment already uses. **A
duplicate-registration bug was found and fixed during this ADR's own
drafting** (see Context finding 2): calling `register_module`
explicitly *and* assigning the attribute registers the same child
twice, visible in `.inspect()`'s child listing. Only one of the two
mechanisms is used, matching the simpler of the two available
patterns in this codebase.

**Q7 — How does the adapter invoke its `Block`?**
`self._block(input, context=context)` — through `Module.__call__`,
exactly as `Sequential.forward` already invokes its own children
(`step(value, context=...)`, not `step.forward(value, context=...)`).
Rejected: calling `self._block.forward(input, context=context)`
directly to avoid a second `ExecutionError` wrap layer — would make
this adapter the *only* place in the codebase that bypasses
`Module.__call__` when invoking a child `Module`, an inconsistency
with `Sequential`'s own established pattern for no benefit once Q8's
correction is applied.

**Q8 — What is the actual failure-propagation contract?**
**Corrected during this ADR's own drafting** (see Context finding 3):
the original exception is reachable by walking the `__cause__` chain
from the raised `ExecutionError`, not necessarily at
`exc.__cause__` directly. A graph-backed `RAGModule`
(`_GraphBackedRAGModule`) wraps once (its own `Module.__call__`); the
`Block` it wraps has already wrapped once (`Block`'s own
`Module.__call__`) — so `exc.__cause__.__cause__` reaches the
original exception for a bare `RAGModule.from_graph(...)` call, and
one additional `__cause__` hop is added for each further `Module`
layer the architecture is nested inside (e.g. one more if placed
inside a `Sequential`). This is `Module.__call__`'s correct, existing,
universal convention — applied consistently, not specially, to
graph-backed `RAGModule` — verified by direct construction against
already-merged `main` behavior for `Block` nested in `Sequential`
(identical wrap-depth pattern), not merely asserted from the ADR text.
No new exception type is introduced; `ExecutionError` is reused at
every layer exactly as it already is.

**Q9 — Does the architecture create its own `Run`/`Trace`/`Metrics`?**
No. `RAGModule.from_graph(...)`'s result is invoked via ordinary
`Module.__call__` (no `ExecutionEngine.execute`/`execute_plan` at the
top level unless a caller explicitly wraps it in one) — the same
"bring your own engine" relationship every other bare `Module`
already has. Internally, `Block.forward` still creates its own
`Run`/`Trace`/`MetricsCollector` via `ExecutionEngine().execute_plan(...)`
(unchanged from ADR-020) — this ADR does not add a second, competing
lifecycle at the `RAGModule` layer on top of that.

**Q10 — Does `from_graph` mutate the supplied graph?** No — matches
`Block`'s own existing immutability guarantee (ADR-020 Q3) exactly;
`from_graph` passes the graph straight to `Block`'s constructor with
no copy, no mutation.

**Q11 — Plan caching, serialization, async?** Not in this ADR — all
three remain exactly as deferred by ADR-020 (Q11/Q12/Q13), inherited
unchanged since this ADR delegates entirely to `Block` for execution.

**Q12 — Provider independence?** `RAGModule.from_graph` and
`_GraphBackedRAGModule` import only `ragtorch.core.block` (`Block`)
and `ragtorch.core.composition` (`CompositionGraph`, for the type
annotation) — no provider SDK, matching every prior layer's discipline.

## Decision

### Naming and location: `RAGModule.from_graph`, `_GraphBackedRAGModule`, `src/ragtorch/core/module.py`

Added to the existing `module.py` (where `RAGModule` already lives),
not a new module — this is an additive classmethod plus one small,
private adapter class, not a new runtime type.

### Public contract

**A fourth finding, caught during 17D implementation (not 17C
drafting)**: `block.py` already imports `from ragtorch.core.module
import Module` at module level (`Block` inherits `Module`). Adding a
module-level `from ragtorch.core.block import Block` to `module.py`
would create a genuine circular import, failing at interpreter import
time — not merely a style concern. `import Block` inside `from_graph`
itself (a deferred/lazy import) resolves this with zero risk, and
mirrors an already-established pattern in this exact file:
`Module.snapshot()` already does `from ragtorch.core.inspection import
snapshot as _snapshot` inside its own method body for the same reason
(`inspection.py` needs `Module` for its type surface). This is
reflected in the contract below — `Block` is imported inside
`from_graph`, not at module scope.

```python
class RAGModule(Module):
    """Marker base class for top-level, RAG-specific systems.

    Its marker semantics are retained for backward compatibility.
    from_graph() is an additive construction path for graph-backed
    architectures; the existing subclass-and-override-forward()
    pattern remains fully supported and unchanged.
    """

    @classmethod
    def from_graph(
        cls,
        graph: CompositionGraph,
        *,
        input_node: str,
        output_node: str,
    ) -> "RAGModule":
        """Build a graph-backed RAGModule delegating execution to Block.

        Returns an actual RAGModule instance (isinstance(result,
        RAGModule) is True) wrapping a Block internally -- no second
        execution system. input_node/output_node are required exactly
        as Block requires them; no entry/exit-node inference. Not
        promised to work on an arbitrary RAGModule subclass in this
        version -- see ADR-021 Q3.
        """
        from ragtorch.core.block import Block  # deferred: avoids a
        # circular import with block.py's own module-level "from
        # ragtorch.core.module import Module" -- mirrors
        # Module.snapshot()'s existing lazy-import pattern in this file.

        block = Block(graph, input_node=input_node, output_node=output_node)
        return _GraphBackedRAGModule(block)


class _GraphBackedRAGModule(RAGModule):
    """Private adapter: a RAGModule that delegates forward() to a
    Block. Not part of the public API -- construct via
    RAGModule.from_graph(), never directly.

    __init__'s `block: Block` annotation is safe without a runtime
    import: module.py already uses `from __future__ import
    annotations` (PEP 563), so annotations are strings, never
    evaluated at import time. Block is imported under TYPE_CHECKING
    for the type checker only -- see the module-level import block
    below."""

    def __init__(self, block: Block) -> None:
        super().__init__()
        self._block = block  # single registration via __setattr__ -- see ADR-021 Q6

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        return self._block(input, context=context)
```

### Why `self._block = block`, not `self.register_module("block", block)` too

See Q6 above — the single most consequential implementation-detail
finding in this ADR, caught by direct construction before being
frozen.

### Why failures propagate via `Module.__call__`, not `Block.forward` directly

See Q7/Q8 above — the second most consequential finding, which
corrected this ADR's own first draft.

## Non-goals

Explicitly deferred, not part of this decision:

- **Any change to `RAGModule`'s class hierarchy, constructor, or the
  existing subclass-and-override-`forward()` pattern.** Zero lines
  touched in that pattern's behavior.
- **`from_graph` on arbitrary `RAGModule` subclasses.** See Q3.
- **A new execution engine, planner, or executor.** Delegates entirely
  to `Block`'s existing, unmodified chain.
- **Plan caching, serialization, async execution.** Inherited as
  deferred from ADR-020 — see Q11.
- **A new exception type.** `ExecutionError` is reused at every layer.
- **Automatic input/output-node inference.** Matches `Block`'s
  existing explicit-only contract.
- **Structured `ArchitectureSnapshot` integration, JSON/Mermaid
  renderers, architecture-level validation, capability metadata.**
  Named as future work in Consequences, not attempted here.

## Alternatives considered

- **`class RAGModule(Block)`.** Rejected — see Q1. Breaks the existing,
  tested subclass pattern.
- **`from_graph` returns a bare `Block`.** Rejected — see Q4. Loses
  `isinstance(x, RAGModule)`, undermining ADR-001's existing marker
  semantics for exactly the callers this ADR serves.
- **Public `GraphBackedRAGModule` type.** Rejected — see Q5. Freezes
  more API surface than the factory alone requires; the private
  adapter keeps internal implementation freedom.
- **Call `self._block.forward(...)` directly to avoid nested
  `ExecutionError` wrapping.** Rejected — see Q7/Q8. Would make this
  adapter uniquely inconsistent with how every other `Module`
  (`Sequential` included) invokes its children; the nested-wrap
  behavior is `Module.__call__`'s correct, existing, universal
  convention, not a defect to route around.
- **Support `from_graph` on arbitrary subclasses now.** Rejected — see
  Q3. No demonstrated need; would require deciding subclass
  constructor/state semantics with no real use case to inform the
  answer.

## Security

`from_graph` performs exactly the operations `Block.__init__` already
establishes as trusted: validating `input_node`/`output_node` exist
and fan-in constraints, then storing the supplied, already-constructed
`CompositionGraph`. No dynamic import, no `eval`/`exec`, no
deserialization, no component resolution from untrusted names — the
graph and its components must already exist as real Python objects
before being passed in. No automatic logging of `input`, intermediate
results, or output, matching `Block`'s and `execution.py`'s existing
documented rule.

## Dependency review

Zero new runtime dependencies. `module.py` gains an import of
`ragtorch.core.block.Block` (already-existing internal module) for
`from_graph`'s implementation and type annotation.

## Compatibility

`RAGModule`'s existing constructor, class hierarchy, and the
subclass-and-override-`forward()` pattern are entirely unchanged —
verified by direct construction (`class MyRAG(RAGModule): def
forward(self, input): ...` continues to work exactly as before, no
new required method, no changed signature). `Module`, `Sequential`,
`Component`, `CompositionGraph`, `Connection`, `ExecutionPlan`,
`Executor`, `ExecutionEngine`, `ExecutionContext`, `Block` — all
unchanged. `RAGModule.from_graph` and `_GraphBackedRAGModule` are a
pure addition to the existing `module.py`; no new public type beyond
`from_graph` itself (the adapter is private).

## Testing strategy

- **RM-01** Existing subclass pattern (`class MyRAG(RAGModule): def
  forward(self, input): ...`) continues to work unmodified — full
  existing `test_module.py` `RAGModule` tests pass unmodified.
- **RM-02** `hasattr(RAGModule, "from_graph")`.
- **RM-03** `isinstance(RAGModule.from_graph(...), RAGModule)` is
  `True`.
- **RM-04** `isinstance(RAGModule.from_graph(...), Module)` is `True`.
- **RM-05/06** Missing `input_node`/`output_node` keyword argument
  fails with `TypeError` (Python's own required-keyword-argument
  enforcement — no custom handling needed).
- **RM-07/08** Invalid `input_node`/`output_node` (not present in the
  graph) raises `ValidationError` — inherited unmodified from `Block`'s
  own construction-time validation, not re-implemented.
- **RM-09** Simple linear graph executes correctly end to end.
- **RM-10** A `Block` can appear as a `GraphNode.component` inside the
  graph passed to `from_graph`.
- **RM-11** A `RAGModule.from_graph(...)` result can itself be placed
  as a `GraphNode.component` inside another graph (proving it
  satisfies `Component` structurally, same as `Block`).
- **RM-12** A `RAGModule.from_graph(...)` result works as a `Sequential`
  child.
- **RM-13** `architecture(value, context=my_context)` preserves the
  supplied context — `Block`'s own `Run.context` for its inner
  `execute_plan` call is exactly the object passed through.
- **RM-14** `architecture(value)` with no context still works,
  matching `Module.__call__`'s existing "no context" path.
- **RM-15** A component failure inside the graph propagates as
  `ExecutionError` out of `architecture(value)`.
- **RM-16 (corrected)** The original exception is reachable by walking
  the `__cause__` chain from the raised `ExecutionError` — for a bare
  `RAGModule.from_graph(...)` call, `exc.__cause__.__cause__` is the
  original exception object (`is`, not merely `isinstance`); one
  additional `__cause__` hop per additional enclosing `Module` layer
  (e.g. `Sequential`). Not `exc.__cause__ is original_error` directly
  — see Q8.
- **RM-17** No provider import in `module.py`'s `from_graph`/
  `_GraphBackedRAGModule` code (AST-based check, reusing the
  established pattern).
- **COMPAT-01** `Block`'s full existing test suite passes unmodified.
- **COMPAT-02** `Sequential`'s full existing test suite passes
  unmodified.
- **COMPAT-03** `Module`'s full existing test suite (including all
  pre-existing `RAGModule` tests) passes unmodified.

## Benchmark strategy

Per ADR-009, `benchmarks/step17_ragmodule_architecture.py`. Compares
`Block(graph, ...)` directly against
`RAGModule.from_graph(graph, ...)` at the same small, fixed chain
lengths ADR-020's own benchmark used (3/10/30 nodes) — this ADR adds
one additional `Module.__call__` layer (`_GraphBackedRAGModule`'s own
event-publishing and exception-wrapping) on top of `Block`'s existing
per-call cost, not a new per-node cost. Reports total time and the
specific overhead the extra `Module.__call__` layer adds over calling
`Block` directly. As with every prior benchmark in this project:
measures, does not prove, an overhead claim; no threshold assertion;
not wired into CI as a blocking gate.

## Consequences

- A caller can build a complete, graph-backed architecture without
  hand-writing `forward()`, while `isinstance(x, RAGModule)` remains
  meaningful for it — directly closing requirement A3's gap, open
  since Step 1.
- `RAGModule`'s existing subclass contract is untouched — both
  construction styles (subclass-and-override, or `from_graph`) are
  valid `RAGModule`s, exactly as ADR-001's marker was always intended
  to recognize "a top-level RAG system" regardless of how it was
  built.
- Failure semantics are stated precisely, not assumed: nested
  `Module.__call__` wrapping is `ExecutionError`-per-layer, consistent
  with `Sequential`'s own existing, already-merged behavior — this ADR
  found and corrected its own first-draft assumption about this before
  any code was written, and the corrected contract (RM-16) is now
  directly regression-tested.
- The `Module.__setattr__` double-registration hazard (Q6) is now a
  documented, tested pitfall (`self._block = block`, not also
  `register_module`) — a concrete implementation detail future
  `Module`-composing code in this codebase can learn from.
- `_GraphBackedRAGModule` stays private, keeping room for a future,
  richer `Architecture` type to replace it internally without breaking
  callers who only ever used `RAGModule.from_graph(...)`.
- Scope stays deliberately narrow: no second execution system, no plan
  caching, no serialization, no async, no arbitrary-subclass factory
  support — consistent with every prior step's discipline.
