# ADR-020: Block as a Reusable Composition Component

## Status

Accepted

Accepted after real GitHub Actions post-merge CI confirmed on the
actual merged `main` SHA — not from PR CI or local checks alone, per
this project's standing rule that "PR green is not proof." Evidence
trail:

- PR #19 (initial contract freeze, 16A-16C): merged `8583d67`,
  post-merge CI run [31980497928](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31980497928),
  382/382 on 3.10/3.11/3.12.
- PR #20 (implementation, 16D-16P): merged `6ca35ca`, post-merge CI
  run [31981239275](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/31981239275),
  406/406 on 3.10/3.11/3.12, lint clean, on commit `6ca35ca`.

## Context

`docs/architecture/v0.1-architecture.md` §2/§4 names `Block` ("a
reusable composition of components... must not require special
runtime treatment") as the layer between `Component` and
`Graph/Architecture`. It has never been implemented. `ADR-016`
(`CompositionGraph`) explicitly deferred it: *"A `Block` type.
`CompositionGraph` is data; `Block` (a reusable, itself-composable
unit built from a graph) remains unimplemented."* `connection.py` and
`ports.py`'s own docstrings independently reference "a future
graph/Block composition layer." Requirement A2 in the requirements
matrix has stood open since Step 1: *"Blocks compose Components |
Sequential exists | Block abstraction not yet formalized."*

Every layer `Block` was deferred pending now exists and is `Accepted`:
`Component` (ADR-010), `InputPort`/`OutputPort`/`check_connection`
(ADR-011/014), `Connection` (ADR-015), `CompositionGraph` (ADR-016),
`ExecutionPlan`/`plan()` (ADR-017), `Executor`/`SequentialExecutor`/
`StepHandler` (ADR-018), `ExecutionEngine.execute_plan` (ADR-019).

Grounded in direct inspection (16A/16B/16C audit) of `sequential.py`,
`module.py`, `component.py`, `composition.py`, `connection.py`,
`ports.py`, `execution_plan.py`, and `engine.py` (full files, not
assumed) — three findings from that audit directly shape this
decision:

1. **`GraphNode.component` is accepted structurally-typed and
   unchecked** — `composition.py`'s own docstring: "no
   `isinstance(component, Component) here) -- ADR-010 prohibits
   `Component` conformance checks on paths that run once per node."
   Confirmed by grep: zero `isinstance(..., Component)` checks exist
   anywhere in `composition.py`/`execution_plan.py`/`execution.py`.
   **Consequence**: anything structurally satisfying `Component` can
   already be placed as a `GraphNode.component` and flow through
   `plan()`/`Executor`/`ExecutionEngine.execute_plan` today, with zero
   changes to any of those layers — the runtime is already
   Block-agnostic by construction, not merely by intent.
2. **No entry/exit-node concept exists anywhere in
   `CompositionGraph`/`ExecutionPlan`.** `ExecutionPlan.steps` is a
   topological order only; a `StepHandler` decides each step's input
   from `context.results` (ADR-018 Q4), which explicitly defers
   multi-dependency aggregation semantics — the same deferral
   `CompositionGraph`'s fan-in ≤ 1 rule made at the graph level
   (ADR-016). There is no basis in any existing layer for inventing an
   implicit "first/last node" convention.
3. **`Module.__init__` takes no arguments anywhere in this codebase**
   — `_name` is always `self.__class__.__name__`, set once via
   `object.__setattr__`, with no override mechanism. Every existing
   `Module` subclass (`Sequential`, `RAGModule`) follows this
   convention with zero exception.

**This ADR does not build a second execution system, does not modify
`Sequential`, `Module`, `CompositionGraph`, `ExecutionPlan`,
`Executor`, or `ExecutionEngine`, does not add plan caching,
serialization, or async execution, and does not decide multi-root or
multi-sink graph semantics.** It answers: given a `CompositionGraph`
built entirely from existing, unmodified primitives, what is the
smallest additive `Block` type that is itself a `Component`, delegates
all execution to the existing `plan()`/`Executor`/`ExecutionEngine`
chain, and can therefore be nested inside another `CompositionGraph`
without the runtime ever needing to know it exists?

```text
Component (Protocol)
      ^
      | structural
      |
  ┌───┴────┐
  │        │
Module    Block (this ADR)
  │        │
Sequential │ owns a CompositionGraph, delegates execution to:
           │
           v
      plan(graph) -> ExecutionPlan -> Executor -> ExecutionEngine.execute_plan
```

## Problem

We need a minimal, provider-independent `Block` type that (a)
structurally satisfies `Component` so it can appear as a
`GraphNode.component` in an *outer* `CompositionGraph` (enabling
nesting) without any runtime change, (b) owns an *inner*
`CompositionGraph` supplied at construction, never mutable through the
`Block`, (c) has an explicit, non-inferred way to map its single
external input to a root node and its single return value from a
sink node — since no layer below provides an implicit answer, (d)
preserves `ExecutionContext` ancestry when nested (never starts a new,
unrelated root), and (e) propagates component failures with the same
semantics the existing runtime already establishes, introducing no
new exception type without a demonstrated need.

## Open questions this ADR must decide before any code is written

**Q1 — Is `Block` a `Protocol` or a concrete class?** A concrete class,
`Block(Module)` — not a `Protocol`. Rejected: `Block` as a bare
`Protocol` (mirroring `Component`'s structural-typing precedent) —
there is a concrete, reusable behavior (own a graph, derive a plan,
execute it) every `Block` instance needs, not merely a shape different
implementations independently satisfy. `Component` is a `Protocol`
because the framework must recognize third-party implementations with
zero `ragtorch` dependency (ADR-010); `Block` has no equivalent
requirement — every `Block` in this version is this framework's own
composition mechanism, exactly as `Sequential` already is. Inheriting
`Module` gives `Block` the existing `register_module`/`children`/
`snapshot`/`inspect` machinery for free and, via `Module.name`/
`component_type`, satisfies `Component` structurally without
reimplementing anything — the same relationship `Sequential` already
has.

**Q2 — Does `Block` accept a `name=` override?** No. Matches
`Module`'s existing, universal convention exactly: `Block`'s name is
`type(self).__name__`, set by `Module.__init__` with zero special
case. **Confirmed during 16C review**: `Module.__init__` takes no
arguments anywhere in this codebase — no existing subclass
(`Sequential`, `RAGModule`) has a name override, and adding one only
for `Block` would be new, asymmetric `Module` behavior this ADR has no
mandate to introduce (see ADR-016 §16C.20's own compatibility rule:
"do not refactor merely for aesthetic consistency"). A caller wanting
a distinctive name subclasses `Block`, exactly as they would today for
`Sequential`.

**Q3 — Is the inner `CompositionGraph` mutable through `Block`?** No.
Supplied once at construction (`Block(graph, input_node=..., output_node=...)`),
exposed read-only via a `graph` property, never mutated by any `Block`
method. Rejected: exposing `block.graph.add_node(...)`-style mutation
— `CompositionGraph` is already immutable/functional-update
(`add_node`/`add_connection` return a *new* graph, ADR-016 A61); a
caller who wants a different graph constructs a new `Block` with it.
Mutability through `Block` would also undermine every future
consumer's ability to treat a `Block`'s composition as a stable,
reproducible fact once constructed — directly relevant to future
caching/serialization/architecture-hashing, none of which this ADR
builds, but none of which this ADR should foreclose either.

**Q4 — How does external input reach the graph, and how does a return
value come out?** Exactly one `input_node` and exactly one
`output_node`, both required, non-optional constructor arguments
naming existing `GraphNode.id`s in the supplied graph. **Corrected
during 16C review** from an initial "infer first/last node" instinct:
no existing layer (`CompositionGraph`, `ExecutionPlan`) has any
entry/exit-node concept, and every layer below has deliberately
deferred multi-dependency aggregation (ADR-016's fan-in ≤ 1,
ADR-018 Q4) — inventing an implicit convention here would either
silently answer a question those ADRs punted on, or produce
inconsistent behavior for any graph with more than one root or sink.
Rejected: supporting multiple input/output nodes with an explicit
mapping now — decides an aggregation question this ADR has no
evidence-based basis to answer yet (no real multi-root/multi-sink
`Block` use case exists to inform the shape); deferred to a future
ADR if one materializes, exactly as ADR-016/018 deferred their own
analogous questions. A graph with more than one node lacking incoming
connections, or more than one node lacking outgoing connections, is
not rejected by this ADR (that remains `CompositionGraph`'s own,
unmodified validation) — `Block` simply requires the caller to name
*which* node is the single entry and *which* is the single exit,
regardless of how many other roots/sinks the graph happens to have.

**Q5 — How does `Block.forward` actually invoke the plan?**
`Block.forward` builds a `StepHandler` closure that: for `input_node`,
returns the `Block`'s own `input` argument (ignoring
`context.results`, since a root node has none); for every other node,
resolves that node's `GraphNode.component` from `self._graph.nodes`
and calls it with **the single upstream result named by its
`ExecutionStep.dependencies`** (this Block requires each non-root
node to have exactly one dependency — see Q4's fan-in reasoning; a
node with more than one dependency is rejected by `Block`'s own
construction-time validation, not deferred to a confusing runtime
failure). It then calls `ExecutionEngine().execute_plan(plan(self._graph),
handler, context=context)` and returns
`result.output.values[self._output_node]`. Rejected: giving the
handler access to `Block`'s `context` for resolving inputs — the
handler only ever needs `context.results` and its own closed-over
`input`/`self._graph`, matching ADR-019 Q2's established boundary that
`ExecutionContext` is not threaded into step work.

**Q6 — Which `Executor`/`ExecutionEngine` does `Block` use?**
`Block.forward` constructs a bare `ExecutionEngine()` (default
`ObservabilityLevel.BASIC`) and a bare `SequentialExecutor()`
(the `execute_plan` default) internally — not caller-configurable in
this version. Rejected: accepting `engine=`/`executor=` parameters on
`Block.__init__` or `forward` — no real requirement has yet
demonstrated a need for a `Block` to use a different `Executor` or
observability level than its default, and adding the parameter now
would freeze API surface speculatively. This is stated as a Non-goal,
not foreclosed structurally — nothing prevents a future ADR from
adding such parameters additively.

**Q7 — Does a nested `Block` preserve `ExecutionContext` ancestry?**
Yes — this is the load-bearing reason `context` flows through
`Block.forward(input, context=None)` at all. When `Block` is invoked
as a `GraphNode.component` inside an *outer* `plan()`/`execute_plan`
call, its `StepHandler` (built by whatever owns the outer graph)
receives no `ExecutionContext` at all per ADR-019 Q2 — meaning a
`Block` nested this way, called from a plan-driven handler, has no
parent context to propagate today, and this ADR does not attempt to
retrofit one (that would require ADR-019's own frozen boundary to
change). When `Block` is invoked directly as a `Module`
(`block(input, context=some_context)`, e.g. as a `Sequential` child,
which already derives `context.child(step=...)` per ADR-007), the
supplied `context` is passed straight through to the inner
`execute_plan(..., context=context)` call, so `Run.context` for the
inner plan execution is exactly the context the outer caller supplied
— preserving root/parent ancestry through `Module`-based nesting
(`Sequential` containing a `Block`), the nesting path this codebase
already has tested precedent for (ADR-007's `Sequential` non-goal:
`context.child(step=...)`).

**Q8 — Is an empty graph a valid `Block`?** No. `CompositionGraph(nodes=(),
connections=())` is structurally valid per ADR-016, but a `Block`
naming an `input_node`/`output_node` that doesn't exist in an empty
graph fails `Block.__init__`'s own validation (see Q9) — an empty
graph can never satisfy "contains a node named `input_node`," so this
requirement is enforced as a consequence of Q9, not a separate rule.

**Q9 — Is graph validity re-checked by `Block`, or trusted from
`CompositionGraph`?** `CompositionGraph.__post_init__` (ADR-016)
already guarantees acyclicity, referential integrity, no duplicate
connections, and fan-in ≤ 1 — `Block` trusts that guarantee rather
than re-validating structure, the same single-source-of-truth
discipline `plan()` (ADR-017) already established one layer down.
`Block.__init__` performs exactly the validation `CompositionGraph`
cannot: that `input_node`/`output_node` name actual `GraphNode.id`s in
the supplied graph, and that every non-`input_node` step in
`plan(graph).steps` has exactly one dependency (Q5's fan-in
requirement, which `CompositionGraph`'s own fan-in ≤ 1 rule does not
by itself guarantee — a node could have zero dependencies without
being the designated `input_node`, which `Block` also rejects, since a
non-entry root has no way to receive a value under this ADR's
contract).

**Q10 — How does a component failure propagate?** Unmodified, matching
the existing `Executor`/`ExecutionEngine.execute_plan` contract
exactly — no new exception type. A component raising inside `Block`'s
handler propagates through `Executor.execute` unwrapped (ADR-018 Q11),
then through `execute_plan` unwrapped (ADR-019 Q9), then out of
`Block.forward` — at which point `Module.__call__` (the outermost
layer `Block` itself runs under, since `Block` is a `Module`) applies
its own existing, unmodified `ExecutionError` wrapping, exactly as it
already does for every other `Module` subclass's `forward()`
exception. Rejected: introducing `BlockExecutionError` or any
`Block`-specific exception type — no existing failure contract in this
codebase is insufficient for this case; a new type would only
duplicate `ExecutionError`'s already-established role for "a
module/component raised during invocation."

**Q11 — Is the `ExecutionPlan` cached across `Block` calls?** No —
`plan(self._graph)` is called fresh inside every `forward()` invocation.
Rejected: caching `self._plan = plan(self._graph)` at construction or
on first call — raises real questions (thread-safety of a shared
cached plan across concurrent `forward()` calls, invalidation if a
future version allows graph replacement, staleness) with no
benchmark evidence yet that planning cost is material relative to
actual component execution cost. Deferred to a future, measurement-
informed ADR if the benchmark (see Benchmark strategy) shows planning
overhead is significant — matching this project's established
"measure before optimizing" discipline (see ADR-018's identical
reasoning for its own O(n²) context-copying cost).

**Q12 — Serialization?** Not implemented. `Block`'s constructor
arguments (`graph`, `input_node`, `output_node`) are already
serialization-friendly data (a `CompositionGraph` of `GraphNode`/
`Connection` values, plus two strings) without this ADR implementing
serialization itself — consistent with `ExecutionPlan`'s own
"kept serialization-friendly without implementing serialization"
precedent (ADR-017).

**Q13 — Async?** Not implemented. `Block.forward` is synchronous only,
matching `Executor`/`execute_plan`'s existing synchronous-only
constraint (ADR-018 Q7, ADR-019 Q16) — introducing async here would
require those layers to support it first.

**Q14 — Does this ADR modify `Sequential`?** No — zero lines touched.
`Sequential(Block)` or `Block` absorbing `Sequential`'s responsibility
is explicitly out of scope; `Sequential` keeps its own, independent,
already-tested semantics. Whether `Sequential` should eventually
become a `Block` (a linear-chain graph is a trivial special case of a
general graph) is a real future question this ADR does not answer,
per the standing "don't refactor merely for aesthetic consistency"
rule.

**Q15 — Public export?** `Block` is added to both
`ragtorch.core.__all__` and top-level `ragtorch.__all__`, matching the
existing 100%-parity convention every prior public type has followed
— no naming collision exists (`Block` is not already used anywhere in
`src/ragtorch`, confirmed via grep before this decision was written).

## Decision

### Naming and location: `Block`, `src/ragtorch/core/block.py`

A new module, not an addition to `sequential.py` (a different,
independent composition primitive) or `composition.py` (a different
concern: `CompositionGraph` is data, `Block` is executable behavior
built on top of it — the exact separation ADR-016 Non-goals already
drew).

### Public contract

```python
from ragtorch.core.composition import CompositionGraph
from ragtorch.core.context import ExecutionContext
from ragtorch.core.engine import ExecutionEngine
from ragtorch.core.errors import ValidationError
from ragtorch.core.execution import StepExecutionContext
from ragtorch.core.execution_plan import ExecutionStep, plan
from ragtorch.core.module import Module


class Block(Module):
    """A reusable, itself-composable execution unit built from a
    CompositionGraph.

    Structurally satisfies Component via Module's existing name/
    component_type properties -- no special case. Owns graph
    immutably (supplied once at construction, exposed read-only);
    delegates all execution to the existing plan()/Executor/
    ExecutionEngine.execute_plan chain -- Block never walks steps,
    resolves components, or schedules anything itself. A single
    input_node/output_node pair is required at construction; multi-
    root/multi-sink graphs and multi-dependency non-entry nodes are
    explicitly rejected in this version -- see ADR-020 Q4/Q5/Q9.
    """

    def __init__(
        self,
        graph: CompositionGraph,
        *,
        input_node: str,
        output_node: str,
    ) -> None:
        super().__init__()
        node_ids = {node.id for node in graph.nodes}
        if input_node not in node_ids:
            raise ValidationError(
                f"Block input_node {input_node!r} is not a node in the supplied graph."
            )
        if output_node not in node_ids:
            raise ValidationError(
                f"Block output_node {output_node!r} is not a node in the supplied graph."
            )
        execution_plan = plan(graph)
        for step in execution_plan.steps:
            if step.node_id != input_node and len(step.dependencies) != 1:
                raise ValidationError(
                    f"Block requires every non-input_node step to have exactly one "
                    f"dependency; step {step.node_id!r} has {len(step.dependencies)}."
                )
        self._graph = graph
        self._input_node = input_node
        self._output_node = output_node

    @property
    def graph(self) -> CompositionGraph:
        return self._graph

    def forward(self, input: object, *, context: ExecutionContext | None = None) -> object:
        components = {node.id: node.component for node in self._graph.nodes}

        def handler(step: ExecutionStep, step_context: StepExecutionContext) -> object:
            if step.node_id == self._input_node:
                return components[step.node_id](input, context=context)
            (dependency,) = step.dependencies
            upstream = step_context.results[dependency]
            return components[step.node_id](upstream, context=context)

        result = ExecutionEngine().execute_plan(plan(self._graph), handler, context=context)
        return result.output.values[self._output_node]
```

Note: the handler above passes `context` (the `Block`'s own,
Module-supplied `ExecutionContext`, if any) straight through to every
inner component call — this is the mechanism that satisfies Q7's
ancestry-preservation requirement without `execute_plan` itself ever
injecting context into the handler (ADR-019 Q2 remains untouched;
`Block`'s handler closes over `context` itself, entirely outside
`execute_plan`'s own contract).

### Why `input_node`'s component still receives `input` through the handler, not bypassing it

`Block`'s `input_node` names a real `GraphNode` with a real
`Component`. The external `input` value is passed *to that
component*, not substituted for its output — `Block(input)` means "run
the graph starting from `input_node` fed with `input`," not "skip
`input_node`'s own computation." This matches how every other node in
the plan already works (a component transforms its upstream value),
keeping the contract uniform rather than special-casing the entry
node's semantics.

## Non-goals

Explicitly deferred, not part of this decision:

- **Multi-root or multi-sink `Block` graphs.** Exactly one
  `input_node`/`output_node` required — see Q4.
- **Multi-dependency non-entry nodes inside a `Block`.** Rejected at
  construction — see Q5/Q9. A future `Block` variant (or a change to
  this one) that supports explicit merge/aggregation nodes is separate,
  evidence-informed future work.
- **Plan caching.** See Q11.
- **Serialization.** See Q12.
- **Async execution.** See Q13.
- **Any change to `Sequential`, `Module`, `Component`,
  `CompositionGraph`, `Connection`, `ExecutionPlan`, `Executor`,
  `SequentialExecutor`, `StepHandler`, `ExecutionEngine`.** Zero lines
  touched in any of them.
- **A `name=` override on `Block` or `Module`.** See Q2.
- **Caller-configurable `Executor`/`ExecutionEngine` on `Block`.** See
  Q6.
- **A new exception type for `Block`-specific failures.** See Q10.

## Alternatives considered

- **`Block` as a bare structural `Protocol`, mirroring `Component`.**
  Rejected — see Q1. No third-party-implementation requirement exists
  for `Block` the way ADR-010 established for `Component`.
- **Infer `input_node`/`output_node` from graph structure (first/last
  topological node).** Rejected — see Q4. No existing layer has any
  entry/exit concept; every layer below has deliberately deferred
  exactly the aggregation question this would silently answer.
- **Accept multiple input/output nodes with an explicit mapping now.**
  Rejected — see Q4. No real use case exists yet to inform the shape;
  deferred rather than guessed.
- **Expose mutable graph access (`block.graph.add_node(...)`).**
  Rejected — see Q3. Undermines reproducibility and any future
  caching/serialization/hashing work without this ADR needing to build
  any of that now.
- **Add a `name=` override to `Block` (and, by necessity, `Module`).**
  Rejected — see Q2. No existing `Module` subclass has this capability;
  adding it only for `Block` is new, asymmetric behavior with no
  demonstrated need, and extending `Module` itself is out of this
  ADR's additive scope.
- **Introduce `BlockExecutionError`.** Rejected — see Q10. No existing
  failure contract is insufficient; `ExecutionError` (via
  `Module.__call__`'s existing, unmodified wrapping) already covers
  this case uniformly with every other `Module`.
- **Cache the derived `ExecutionPlan`.** Rejected for this version —
  see Q11. No benchmark evidence yet that planning cost is material;
  deferred pending measurement, matching ADR-018's identical precedent.

## Security

`Block.forward` performs exactly the operations `execute_plan`
already establishes as trusted: invoking caller-supplied `Component`s
via a `StepHandler` closure. No dynamic import, no `eval`/`exec`, no
network operation of its own, no automatic logging of `input`,
intermediate step results, or the final output — those may contain
sensitive data this module knows nothing about, matching
`execution.py`'s and `engine.py`'s existing documented rule. No new
trust boundary beyond what `Module.__call__`/`ExecutionEngine.execute_plan`
already establish.

## Dependency review

Zero new runtime dependencies. `block.py` imports
`ragtorch.core.composition` (`CompositionGraph`),
`ragtorch.core.context` (`ExecutionContext`), `ragtorch.core.engine`
(`ExecutionEngine`), `ragtorch.core.errors` (`ValidationError`),
`ragtorch.core.execution` (`StepExecutionContext`),
`ragtorch.core.execution_plan` (`ExecutionStep`, `plan`), and
`ragtorch.core.module` (`Module`) — all already-existing internal
modules, no provider SDK, no new package.

## Compatibility

No changes to `Component`, `Module`, `Sequential`, `RAGModule`,
`CompositionGraph`, `GraphNode`, `Connection`, `InputPort`/
`OutputPort`, `ExecutionPlan`, `ExecutionStep`, `plan()`, `Executor`,
`SequentialExecutor`, `StepHandler`, `StepExecutionContext`,
`StepExecutionResult`, `ExecutionEngine`, `ExecutionEngine.execute`,
`ExecutionEngine.execute_plan`. `Block` is a pure addition in a new
module, exported bare as `Block` in both `ragtorch.core.__all__` and
`ragtorch.__all__` (no collision — confirmed via grep before this
decision, per Q15).

## Testing strategy

- **CONSTRUCT-01** A `Block` built from a valid single-chain graph
  (`input_node` → ... → `output_node`, every intermediate node with
  exactly one dependency) constructs successfully.
- **CONSTRUCT-02** `input_node` not present in the graph raises
  `ValidationError` at construction, before any execution is possible.
- **CONSTRUCT-03** `output_node` not present in the graph raises
  `ValidationError` at construction.
- **CONSTRUCT-04** An empty graph (`CompositionGraph(nodes=(),
  connections=())`) raises `ValidationError` at construction (via
  CONSTRUCT-02/03 — no node can ever be found).
- **CONSTRUCT-05** A node with more than one dependency (fan-in from
  two upstream nodes into a single non-`input_node` step) raises
  `ValidationError` at construction — see Q5/Q9.
- **CONTRACT-01** `isinstance(block, Component)` is `True` — `Block`
  satisfies the structural `Component` protocol via `Module`'s
  existing `name`/`component_type` properties, with no special case.
- **CONTRACT-02** `block.name == type(block).__name__`, matching every
  other `Module` subclass's existing convention (see Q2).
- **CONTRACT-03** `block.graph is` the exact `CompositionGraph`
  instance supplied at construction — identity-checked, not merely
  equality-checked, and no method on `Block` mutates it.
- **EXEC-01** A single-node `Block` (`input_node == output_node`)
  passes `input` to that node's component and returns its output
  directly.
- **EXEC-02** A 3-node linear chain `Block` (retrieve → rerank →
  generate, mirroring the pattern already established in
  `tests/integration/test_engine_plan_boundary.py`) produces the
  expected composed output, with each intermediate component actually
  invoked in dependency order (verified via a recording fake).
- **EXEC-03** `Block.forward` derives a fresh `plan(self._graph)` on
  every call — verified by confirming two successive calls both invoke
  every node's component the expected number of times (no caching
  artifact silently skips execution on a second call).
- **NEST-01** A `Block` used as a `GraphNode.component` inside an
  *outer* `CompositionGraph` executes correctly when that outer
  graph's own plan is run — proving the "no runtime change needed for
  nesting" claim end-to-end, not merely asserted from the audit.
- **NEST-02** A `Block` nested as a child of a `Sequential`
  (`Sequential(retriever, block, generator)`) receives a
  `context.child(step=...)`-derived `ExecutionContext` from
  `Sequential.forward` (ADR-007's existing mechanism) and threads that
  same context into its own inner `execute_plan` call — the inner
  `Run.context` for the `Block`'s own plan execution is exactly that
  child context, proving Q7's ancestry-preservation claim, not merely
  asserted.
- **NEST-03** A `Block` containing another `Block` (as a
  `GraphNode.component` inside the outer `Block`'s graph) executes
  correctly at two levels of nesting.
- **FAIL-01** A component raising inside a `Block`'s graph propagates
  out of `block(input)` as `ExecutionError` (via `Module.__call__`'s
  existing, unmodified wrapping), with the original exception
  accessible as `exc.__cause__` — matching every other `Module`
  subclass's existing, tested failure convention. No new exception
  type is introduced — see Q10.
- **FAIL-02** A failure in a non-terminal node of the graph prevents
  any downstream node from executing (verified via a recording fake
  that must never receive a call for nodes after the failing one) —
  inherited from `Executor`'s own existing FAIL-03 guarantee, verified
  again here end-to-end through `Block`.
- **COMPAT-01** `Sequential`'s full existing test suite passes
  unmodified.
- **COMPAT-02** `CompositionGraph`/`ExecutionPlan`/`execution.py`/
  `engine.py`'s full existing test suites pass unmodified.
- **SEC-01** No automatic logging of `input`, intermediate step
  results, or `Block`'s return value (source-inspection or behavioral
  test, reusing the established pattern).
- **API-01** `Block` appears in both `ragtorch.core.__all__` and
  `ragtorch.__all__`, verified by the existing public API parity test.

## Benchmark strategy

Per ADR-009, `benchmarks/step16_block_composition.py`. Compares direct
component-chain invocation (no `Block`, calling each component
function by hand in sequence) against an equivalent `Block`-wrapped
graph, at small, fixed chain lengths (3/10/30 nodes — this is not a
scaling benchmark like ADR-017/018's, since `Block` adds one
`plan()` call plus one `execute_plan()` call per `forward()`, not a
per-node cost beyond what `plan()`/`Executor` already independently
cost). Reports total time and the specific overhead `Block`'s
per-call `plan()` re-derivation (Q11) adds over a pre-built
`ExecutionPlan`. As with every prior benchmark in this project:
measures, does not prove, an overhead claim; no threshold assertion;
not wired into CI as a blocking gate (matching Steps 13-15's
precedent). This measurement is the explicit evidence gate for Q11's
deferred plan-caching decision — if it shows re-planning cost is
material at realistic `Block` sizes, that becomes a future ADR's
starting evidence, not something guessed at here.

## Consequences

- `RAG-MODULE` gains its first working instance of the architecture
  doc's full intended stack: `Component → Block → Graph → Runtime`,
  closing a gap requirement A2 has held open since Step 1.
- The runtime required zero changes to support `Block` — direct,
  tested proof (NEST-01/NEST-03) of the "must not require special
  runtime treatment" requirement the architecture doc named for
  `Block` from the start, not merely a design intention.
- `Block`'s single-input-node/single-output-node/single-dependency
  constraint is deliberately conservative, mirroring
  `CompositionGraph`'s own fan-in ≤ 1 precedent (ADR-016) — multi-root/
  multi-sink/multi-dependency `Block` semantics remain explicit,
  evidence-gated future work, not silently invented here.
- `Block` re-derives its `ExecutionPlan` on every `forward()` call; the
  benchmark this ADR requires is the explicit gate for whether that
  cost ever needs revisiting — not assumed acceptable or unacceptable
  without measurement.
- No new exception type, no new public context type, no serialization,
  no async, no caller-configurable executor — scope stays deliberately
  narrow, consistent with every prior step's discipline.
