# Step 16 Evaluation — Block Composition

Date: 2026-08-17

Branch: `feat/step16-block-composition`, based on `main` after ADR-020
was drafted per the 16A/16B/16C audit (docs not yet merged as of this
implementation — see "Completion record" below for the actual merge
sequence, matching Steps 13-15's docs-first-then-implementation
pattern).

## Scope

Framework/architecture feature, not RAG quality. Per ADR-020, this
evaluation proves: given a `CompositionGraph` built entirely from
existing, unmodified primitives, does `Block` (a) structurally satisfy
`Component`, (b) delegate all execution to the existing, unmodified
`plan()`/`Executor`/`ExecutionEngine.execute_plan` chain with zero
runtime-layer changes required, (c) correctly enforce its explicit
`input_node`/`output_node`/single-dependency contract at construction,
(d) preserve `ExecutionContext` ancestry when nested inside
`Sequential`, and (e) support being nested as a `GraphNode.component`
inside another graph (including another `Block`'s graph) — fulfilling
requirement A2 ("Blocks compose Components... Block abstraction not
yet formalized"), open since Step 1.

## The audit that shaped this implementation

16A/16B/16C's repository audit (grounded in direct inspection of
`sequential.py`, `module.py`, `component.py`, `composition.py`,
`connection.py`, `ports.py`, `execution_plan.py`, `engine.py` — full
files, not assumed) found three facts that directly determined the
design, all now verified true by this implementation's own test suite:

- **`GraphNode.component` is accepted structurally-typed and
  unchecked** — confirmed by grep: zero `isinstance(..., Component)`
  calls exist anywhere in the composition/execution stack. This
  ADR-020's central claim ("the runtime is already Block-agnostic")
  is directly proven, not merely asserted, by NEST-01/NEST-03 below:
  a `Block` placed as a `GraphNode.component` in an outer graph
  executes correctly with zero code in `composition.py`,
  `execution_plan.py`, `execution.py`, or `engine.py` aware that
  `Block` exists.
- **No entry/exit-node concept exists anywhere in
  `CompositionGraph`/`ExecutionPlan`.** Confirmed the design decision
  to require explicit `input_node`/`output_node` rather than inferring
  them — CONSTRUCT-02/03 test that omission/typo is rejected at
  construction, not silently guessed at.
- **`Module.__init__` takes no arguments anywhere in this codebase.**
  `Block` follows this convention exactly — CONTRACT-02 verifies
  `block.name == type(block).__name__`, matching every other `Module`
  subclass with zero special case.

## Contract

```python
class Block(Module):
    def __init__(self, graph: CompositionGraph, *, input_node: str, output_node: str) -> None: ...

    @property
    def graph(self) -> CompositionGraph: ...

    @property
    def input_node(self) -> str: ...

    @property
    def output_node(self) -> str: ...

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any: ...
```

Added as a new module `src/ragtorch/core/block.py` — no changes to
`sequential.py`, `composition.py`, or any other existing module.
`Block.__init__` validates `input_node`/`output_node` exist in the
graph and that every non-`input_node` step (derived via `plan(graph)`)
has exactly one dependency, raising `ValidationError` on either
violation — trusting `CompositionGraph.__post_init__`'s own structural
guarantees (acyclicity, referential integrity, fan-in ≤ 1) rather than
re-validating them. `Block.forward` derives a fresh
`plan(self._graph)` on every call (not cached — see "Performance"
below) and builds a `StepHandler` closure resolving each node's
`GraphNode.component`, calling `ExecutionEngine().execute_plan(...)`
and returning `result.output.values[self._output_node]`.

## Correctness

| Invariant | Expected | Result |
| --- | --- | --- |
| Valid linear graph constructs successfully | PASS | PASS |
| Nonexistent `input_node` rejected at construction | PASS | PASS |
| Nonexistent `output_node` rejected at construction | PASS | PASS |
| Empty graph rejected at construction | PASS | PASS |
| Multi-dependency non-entry node rejected at construction | PASS | PASS |
| Non-`CompositionGraph` argument rejected with `TypeError` | PASS | PASS |
| `Block` satisfies `Component` structurally | PASS | PASS |
| `block.name == type(block).__name__` (no name override) | PASS | PASS |
| `block.graph is` the exact supplied graph (no copy) | PASS | PASS |
| Single-node `Block` returns component output directly | PASS | PASS |
| Linear chain composes correctly (2→AddOne→3→MultiplyTwo→6) | PASS | PASS |
| Plan re-derived each call, not silently skipped on repeat calls | PASS | PASS |
| `input_node`'s component receives the external `input`, not upstream results | PASS | PASS |
| Downstream node receives upstream node's result | PASS | PASS |
| `output_node`'s result returned, not the topologically-last step's | PASS | PASS |

```
invariant_count: 15
case_count: 21 (unit) + 3 (integration) = 24
error_count: 0
expected_outcome_accuracy: 1.0
```

## Nesting results (the central architectural claim, verified end-to-end)

| Invariant | Result |
| --- | --- |
| A `Block` as a `GraphNode.component` inside an outer `CompositionGraph`'s `Block` executes correctly | PASS |
| A `Block` as a `Sequential` child preserves `ExecutionContext` ancestry — child `run_id != root.run_id`, child `parent_run_id == root.run_id` (verified via a recording fake, not merely asserted) | PASS |
| A `Block` containing another `Block` (two levels of nesting) executes correctly | PASS |
| End-to-end: `Sequential(Module, Block(3-node RAG-shaped graph))` produces the expected composed output through the real public `ragtorch` import surface | PASS |

## Failure semantics

| Invariant | Result |
| --- | --- |
| A component failure inside `Block`'s graph propagates as `ExecutionError` via `Module.__call__`'s existing, unmodified wrapping | PASS |
| Original exception accessible as `exc.__cause__` | PASS |
| No `Block`-specific exception type introduced — `type(exc_info.value) is ExecutionError` exactly, not a subclass | PASS |
| Downstream nodes never execute after a mid-graph failure (verified via a recording fake that must never receive a call) | PASS |
| Failure propagates correctly through `Sequential(Module, Block)` nesting | PASS |

## Functional results

24 new tests: 21 unit in `tests/unit/core/test_block.py` (mechanism-
level, per the CONSTRUCT/CONTRACT/EXEC/NEST/FAIL matrix) plus 3
integration in `tests/integration/test_block_composition.py`
(end-to-end through the public `ragtorch` import surface — a 3-node
RAG-shaped graph, `Block` nested inside `Sequential`, and failure
propagation through that nesting).

Combined with the pre-existing 382 (unmodified), total suite is
382 + 24 = 406, confirmed by direct `pytest` run, not assumed.

| Invariant | Result |
| --- | --- |
| `Sequential`'s full existing test suite (`test_sequential.py`, `test_sequential_context.py`) passes unmodified | PASS |
| `CompositionGraph`'s full existing test suite (`test_composition.py`) passes unmodified | PASS |
| `ExecutionPlan`'s full existing test suite (`test_execution_plan.py`) passes unmodified | PASS |
| `Executor`'s full existing test suite (`test_execution.py`) passes unmodified | PASS |
| `ExecutionEngine`'s full existing test suites (`test_engine.py`, `test_engine_plan_execution.py`, `test_nested_execution.py`, `test_engine_plan_boundary.py`) pass unmodified | PASS |

## Test results

```
pytest:        406 passed (382 pre-existing, unmodified + 21 unit + 3 integration)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 27 source files
coverage:      block.py 100%; overall 99%
```

Also verified directly against Python 3.10 (`py -3.10`): 406/406
passed.

## Performance

`benchmarks/step16_block_composition.py`, Windows, Python 3.12.0,
local. Compares a direct, hand-written component-chain invocation
(no graph/plan/executor at all) against an equivalent `Block`-wrapped
graph, at 3/10/30-node chains — small, fixed sizes chosen because
`Block` adds a per-call cost (one `plan()` derivation plus one
`execute_plan()` call), not a new per-node cost beyond what `plan()`
already independently costs (already benchmarked at much larger scale
in Step 13).

| Nodes | Direct µs/call | Block µs/call | Overhead µs/call |
| ---: | ---: | ---: | ---: |
| 3 | 0.31 | 14.13 | 13.82 |
| 10 | 0.68 | 23.98 | 23.30 |
| 30 | 2.02 | 55.23 | 53.21 |

### Interpretation

This benchmark measures, it does not prove, an overhead bound.
Overhead is **not** constant across these three sizes — it grows from
~14µs at 3 nodes to ~53µs at 30 nodes, roughly tracking the graph
size rather than staying flat. This is the honest, expected
consequence of `Block.forward` re-deriving `plan(self._graph)` on
every call (ADR-020 Q11): `plan()` itself is O(V+E) (established in
Step 13's own benchmark), so re-deriving it every `forward()` call
adds a cost that scales with graph size, on top of the roughly-fixed
`ExecutionEngine.execute_plan()` lifecycle overhead (`Run`/`Trace`/
`MetricsCollector` construction, already measured in Step 15's
benchmark at tens of microseconds per call).

At the absolute scale this measures (30-node graph, ~53µs total
overhead), the cost is still negligible for realistic single-call RAG
pipeline usage. But the growth trend, not just the absolute numbers,
is real evidence bearing directly on ADR-020 Q11's deferred
plan-caching decision: **if a future `Block` use case involves either
much larger graphs or very high call-frequency reuse of the same
`Block` instance, this benchmark's own trend line is the starting
evidence a future, measurement-informed ADR should build from** — not
re-guessed at that point, and not preemptively "fixed" here without a
demonstrated need, per this project's standing discipline.

## Compatibility review

| Existing API | Step 16 effect |
| --- | --- |
| `Module`/`Sequential`/`RAGModule` | none — zero lines touched |
| `Component` | none — zero lines touched |
| `CompositionGraph`/`GraphNode`/`Connection` | none — zero lines touched |
| `InputPort`/`OutputPort`/`check_connection` | none — zero lines touched |
| `ExecutionPlan`/`ExecutionStep`/`plan()` | none — zero lines touched |
| `Executor`/`SequentialExecutor`/`StepHandler`/`StepExecutionContext`/`StepExecutionResult` | none — zero lines touched |
| `ExecutionEngine`/`ExecutionEngine.execute`/`ExecutionEngine.execute_plan` | none — zero lines touched |
| `ExecutionContext` | none — zero lines touched |
| existing exceptions | unchanged — no new exception type introduced |

Explicitly verified via `git diff` against every protected file
(`module.py`, `sequential.py`, `component.py`, `composition.py`,
`connection.py`, `ports.py`, `execution_plan.py`, `execution.py`,
`engine.py`, `context.py`): zero output, confirming none were touched.
All 382 pre-existing tests pass **unmodified**.

## Security review

| Question | Answer |
| --- | --- |
| Does `Block.forward` perform any operation with external effect itself? | No — only calls caller-supplied components via a `StepHandler` closure and engine-owned `Run`/`Trace`/`Metrics` bookkeeping |
| Does it evaluate annotations, use reflection, `eval`, or `exec`? | No |
| Does it import any provider/model dependency? | No — imports only already-existing internal modules |
| Does it automatically log `input`, intermediate step results, or the final output? | No — matches `execution.py`/`engine.py`'s existing documented rule |
| Does `Block` introduce a new trust boundary? | No — component invocation is trusted application code, exactly as `Module.__call__`/`ExecutionEngine.execute_plan` already establish |

## Dependency review

Zero new runtime dependencies. `block.py` imports
`ragtorch.core.composition` (`CompositionGraph`),
`ragtorch.core.engine` (`ExecutionEngine`), `ragtorch.core.errors`
(`ValidationError`), `ragtorch.core.execution_plan` (`plan`), and
`ragtorch.core.module` (`Module`) — all already-existing internal
modules, no provider SDK, no new package.

## Diff review

Scope: `src/ragtorch/core/block.py` (new),
`tests/unit/core/test_block.py` (new, 21 tests),
`tests/integration/test_block_composition.py` (new, 3 tests),
`benchmarks/step16_block_composition.py` (new),
`src/ragtorch/core/__init__.py` (modified: `Block` import/export),
`src/ragtorch/__init__.py` (modified: `Block` import/export,
docstring update), `tests/unit/test_public_api.py` (modified: `Block`
added to expected exports). ADR-020 and requirements matrix A68 were
drafted in the prior 16A-16C phase. No touch to any protected runtime
file — confirmed by explicit `git diff` against each one, all showing
zero output.

## Known limitations (explicitly named, not silently absorbed)

- **Single `input_node`/`output_node` only.** Multi-root or
  multi-sink `Block` graphs are rejected — explicit ADR-020 Non-goal,
  deferred pending a real use case.
- **Every non-entry node must have exactly one dependency.**
  Multi-dependency merge/aggregation nodes inside a `Block` are
  rejected at construction — mirrors `CompositionGraph`'s own fan-in
  ≤ 1 precedent; deferred, not silently decided.
- **No plan caching.** `Block.forward` re-derives `plan(self._graph)`
  on every call. The benchmark above shows this cost grows with graph
  size, not flat — explicit evidence for, not against, revisiting this
  in a future ADR if a real use case demonstrates the need.
- **No `name=` override.** `Block`'s name is always
  `type(self).__name__`, matching every other `Module` subclass with
  zero special case — a caller wanting a distinctive name subclasses
  `Block`.
- **No caller-configurable `Executor`/`ExecutionEngine`.** `Block`
  always constructs a bare `ExecutionEngine()` (default
  `ObservabilityLevel.BASIC`) and relies on `execute_plan`'s default
  `SequentialExecutor()` internally.
- **No serialization.** `Block`'s constructor arguments are already
  serialization-friendly data without this implementation building
  serialization itself.
- **`ExecutionContext` propagation into a `Block` nested as an outer
  plan's `GraphNode.component` (not as a `Sequential` child) is not
  possible in this version** — a `StepHandler` never receives
  `ExecutionContext` at all (ADR-019 Q2), so a `Block` invoked that way
  has no parent context to thread through. Only the `Module`-based
  nesting path (`Sequential` containing a `Block`) has context
  ancestry, verified by NEST-02.

## Decision

**Step 16 implementation Definition of Done: met locally** (Python
3.10 and 3.12 both verified, 406/406, lint/format/mypy clean,
`block.py` 100% coverage). ADR-020's status remains `Proposed` and A68's
evidence remains local-only until real CI confirms it — per the
project's standing rule that local checks are not CI, and per Steps
13-15's precedent that an ADR is flipped to `Accepted` only after
independent post-merge CI confirmation on the actual merged `main`
SHA.

## Completion record

Pending PR creation (docs-only ADR-020 + A68, then a separate
implementation PR, matching Steps 13-15's exact discipline), PR CI,
merge, and post-merge CI on `main` for both — this section is
completed only after all of those are independently confirmed.
