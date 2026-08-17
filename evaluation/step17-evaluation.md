# Step 17 Evaluation — Graph-backed RAGModule Architecture

Date: 2026-08-17

Branch: `feat/step17-ragmodule-architecture`, based on `main` after
ADR-021 was drafted per the 17A/17B/17C audit (docs not yet merged as
of this implementation — see "Completion record" below for the actual
merge sequence, matching Steps 13-16's docs-first-then-implementation
pattern).

## Scope

Framework/architecture feature, not RAG quality. Per ADR-021, this
evaluation proves: given a `CompositionGraph`, does
`RAGModule.from_graph(graph, *, input_node, output_node)` produce an
actual `RAGModule` instance that (a) preserves `isinstance(x,
RAGModule)`, (b) delegates all execution to the existing, unmodified
`Block`/`plan()`/`Executor`/`ExecutionEngine.execute_plan` chain, (c)
does not change `RAGModule`'s existing subclass-and-override-`forward()`
contract in any way, (d) registers exactly one child (`_block`), and
(e) has an accurately-stated failure-propagation contract — fulfilling
requirement A3, open since Step 1.

## 1 = Contract

| Item | Result |
| --- | --- |
| `RAGModule.from_graph` exists as a classmethod | PASS |
| Returns an actual `RAGModule` instance | PASS |
| Also satisfies `isinstance(x, Module)` and `Component` | PASS |
| `RAGModule`'s existing constructor/hierarchy unchanged | PASS |
| Delegates entirely to `Block` — no second execution system | PASS |
| Exactly one registered child (`_block`) | PASS |
| No new exception type | PASS |

## 2 = Correctness

| Item | Result |
| --- | --- |
| Linear graph executes correctly | PASS |
| `Block` can appear as a `GraphNode.component` inside the graph passed to `from_graph` | PASS |
| A `from_graph` result can itself be a `GraphNode.component` in another graph | PASS |
| A `from_graph` result works as a `Sequential` child | PASS |
| Context propagation preserved (`architecture(value, context=ctx)`) | PASS |
| No-context call still works | PASS |
| Failure propagation (corrected contract — see below) | PASS |
| Downstream failure behavior inherited from `Block`/`Executor` (no partial execution) | PASS |

## 3 = Compatibility

| Item | Result |
| --- | --- |
| `Module`'s full existing test suite (including all pre-existing `RAGModule` tests) passes unmodified | PASS |
| `Sequential`'s full existing test suite passes unmodified | PASS |
| `CompositionGraph`/`ExecutionPlan`/`Executor`/`ExecutionEngine` test suites pass unmodified | PASS |
| `Block`'s full existing test suite passes unmodified | PASS |
| Existing subclass-and-override-`forward()` pattern (`class MyRAG(RAGModule): def forward(self, input): ...`) works exactly as before | PASS |

## 4 = Security

| Item | Result |
| --- | --- |
| No user-input logging | PASS |
| No intermediate-result logging | PASS |
| No output logging | PASS |
| No secret extraction, no dynamic import, no `eval`/`exec` | PASS |

## 5 = Performance

| Nodes | Block µs/call | RAGModule µs/call | Overhead µs/call |
| ---: | ---: | ---: | ---: |
| 3 | 62.39 | 74.57 | 12.18 |
| 10 | 95.21 | 164.07 | 68.86 |
| 30 | 206.71 | 245.07 | 38.36 |

## 6 = Architecture

| Item | Result |
| --- | --- |
| No runtime special case (zero changes to `block.py`, `composition.py`, `execution_plan.py`, `execution.py`, `engine.py`) | PASS |
| No new runtime dependency | PASS |
| No provider dependency | PASS |
| No unnecessary abstraction (`_GraphBackedRAGModule` stays private, minimal) | PASS |
| No unresolved architectural question — see "Deferred decisions" | N/A |

## The audit findings that shaped this implementation (all four verified true by the test suite)

17A/17B/17C/17D's repository audit (grounded in direct inspection of
`module.py`, `block.py`, `sequential.py`, `test_module.py` — full
files, not assumed) found and corrected four issues before the ADR was
frozen or any code committed:

1. **`class RAGModule(Block)` would break the existing, tested
   subclass pattern.** Rejected outright before drafting a contract
   around it — confirmed by `test_rm_01_existing_subclass_pattern_still_works`
   passing unmodified.
2. **A double-registration hazard**: `Module.__setattr__`
   auto-registers any `Module`-valued attribute assignment; calling
   `register_module` explicitly *and* assigning the attribute
   registers the same child twice. Caught by direct construction and
   `.inspect()` inspection before being frozen into the ADR; fixed to
   a single `self._block = block` assignment — directly regression-
   tested by `test_block_registered_exactly_once`.
3. **A false single-hop failure-identity assumption**
   (`exc.__cause__ is original_error`) in this ADR's own first draft,
   disproven by direct construction against already-merged `main`
   behavior (`Block` nested in `Sequential` already produces a
   two-layer `ExecutionError` chain today) — corrected to the accurate
   walked-`__cause__`-chain contract, directly regression-tested by
   `test_rm_16_original_exception_reachable_via_cause_chain` and
   `test_failure_wrap_depth_increases_by_one_when_nested_in_sequential`.
4. **A circular-import hazard found during 17D implementation itself**
   (not caught during 17C drafting): `block.py` imports `Module` from
   `module.py` at module scope; adding a module-level `Block` import
   to `module.py` would create a genuine circular import, failing at
   interpreter import time. Resolved via a deferred import inside
   `from_graph` itself, mirroring `Module.snapshot()`'s own existing
   lazy-import pattern in this exact file (`from
   ragtorch.core.inspection import snapshot as _snapshot`) — not a
   new pattern invented for this ADR.

## Contract

```python
class RAGModule(Module):
    @classmethod
    def from_graph(
        cls, graph: CompositionGraph, *, input_node: str, output_node: str
    ) -> RAGModule: ...


class _GraphBackedRAGModule(RAGModule):
    def __init__(self, block: Block) -> None: ...
    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any: ...
```

Added to the existing `src/ragtorch/core/module.py` — no new module.
`Block` is imported lazily inside `from_graph` (see finding 4 above)
and, for type-annotation purposes only, under `TYPE_CHECKING` at
module scope (safe without a runtime import because `module.py`
already uses `from __future__ import annotations`, PEP 563 — no
annotation is evaluated at import time).

## Execution delegation

`_GraphBackedRAGModule.forward` calls `self._block(input,
context=context)` — through `Module.__call__`, exactly as
`Sequential.forward` already invokes its own children (`step(value,
context=...)`, not `step.forward(...)`). This was a deliberate
decision, not an oversight: an earlier consideration (calling
`self._block.forward(...)` directly to get a single-hop `__cause__`)
was rejected because it would make this adapter uniquely inconsistent
with how every other `Module` in this codebase composes children — see
finding 3 above.

## Context behavior

`architecture(value, context=my_context)`'s `context` threads straight
into `Block.forward`'s own `execute_plan(..., context=context)` call —
`Block`'s inner `Run.context` for that call is exactly the object the
caller supplied to the architecture, verified by
`test_rm_13_context_preserved`. No second, competing context mechanism
is introduced at the `RAGModule` layer.

## Failure behavior (corrected contract)

`ExecutionError` is reused at every `Module.__call__` layer the
architecture passes through — never a new exception type. For a bare
`RAGModule.from_graph(...)` call:
`exc.__cause__` is the `ExecutionError` `Block`'s own `Module.__call__`
raised, and `exc.__cause__.__cause__` is the original exception
(`is`, exact identity — verified, not merely `isinstance`-checked).
One additional `__cause__` hop is added per additional enclosing
`Module` layer (verified for `Sequential` nesting:
`exc.__cause__.__cause__.__cause__` reaches the original exception).
This is `Module.__call__`'s correct, existing, universal convention —
this ADR does not special-case it.

## Observability

`_GraphBackedRAGModule` creates no `Run`/`Trace`/`MetricsCollector` of
its own — `architecture(value)` alone, with no `ExecutionEngine`
involved at the top level, behaves exactly like calling any other bare
`Module`. `Block.forward`'s own `Run`/`Trace`/`MetricsCollector`
creation (unchanged from ADR-020) remains the only lifecycle
instrumentation in the whole call chain — no duplicate or competing
lifecycle is introduced.

## Provider independence

`module.py`'s new `from_graph`/`_GraphBackedRAGModule` code imports
only `ragtorch.core.block` (`Block`, deferred) and
`ragtorch.core.composition` (`CompositionGraph`, `TYPE_CHECKING` only)
— both already-existing internal modules. AST-based check
(`test_rm_17_module_has_no_provider_imports`) confirms no
provider-name substring appears in any import anywhere in `module.py`.

## Nested composition

Verified end-to-end, not merely asserted:

- A `Block` as a `GraphNode.component` inside the graph passed to
  `from_graph` (`test_rm_10_block_as_graph_node_inside_from_graph`).
- A `RAGModule.from_graph(...)` result placed as a `GraphNode.component`
  in another `CompositionGraph`, executed via a `Block` wrapping that
  graph (`test_rm_11_from_graph_result_can_be_a_graph_node_component`).
- A `RAGModule.from_graph(...)` result used as a `Sequential` child
  (`test_rm_12_from_graph_result_works_as_sequential_child`).

All three work with zero changes to `block.py`, `composition.py`,
`execution_plan.py`, `execution.py`, or `engine.py` — the same "boring
to the runtime" property `Block` itself established in Step 16, now
also holding for graph-backed `RAGModule`.

## Functional results

25 new tests: 21 unit in `tests/unit/core/test_ragmodule_architecture.py`
(mechanism-level, per the ADR-021 RM/COMPAT matrix) plus 4 integration
in `tests/integration/test_ragmodule_from_graph.py` (end-to-end
through the real public `ragtorch` import surface — a RAG-shaped
3-node graph, nesting inside `Sequential`, a `Block` node inside the
architecture's own graph, and failure propagation through `Sequential`
nesting — renamed from a would-be
`test_ragmodule_architecture.py` to avoid this repository's
established rootless-layout pytest module-basename collision with the
unit test file, the same class of issue Steps 13/14/16 all hit and
resolved the same way).

Combined with the pre-existing 406 (unmodified), total suite is
406 + 25 = 431, confirmed by direct `pytest` run, not assumed.

## Test results

```
pytest:        431 passed (406 pre-existing, unmodified + 21 unit + 4 integration)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 27 source files
coverage:      module.py 99% (2 lines uncovered, both pre-existing:
                RegistryError re-raise branches unrelated to Step 17);
                overall 99%
```

Also verified directly against Python 3.10 (`py -3.10`): 431/431
passed.

## Performance

`benchmarks/step17_ragmodule_architecture.py`, Windows, Python
3.12.0, local. Compares `Block(graph, ...)` directly against
`RAGModule.from_graph(graph, ...)` at 3/10/30-node chains, isolating
the additional `Module.__call__` layer's cost.

| Nodes | Block µs/call | RAGModule µs/call | Overhead µs/call |
| ---: | ---: | ---: | ---: |
| 3 | 62.39 | 74.57 | 12.18 |
| 10 | 95.21 | 164.07 | 68.86 |
| 30 | 206.71 | 245.07 | 38.36 |

### Interpretation

This benchmark measures, it does not prove, an overhead bound.
Overhead is small (tens of microseconds) at all three sizes measured,
consistent with the added cost being exactly one `Module.__call__`
layer (`_GraphBackedRAGModule`'s own event-publishing and
exception-wrapping) rather than a per-node cost — it does not
systematically grow with node count the way `Block`'s own already-
benchmarked `plan()`-re-derivation cost does (Step 16). The
measurements are noisier than a perfectly flat line (10-node showed
higher overhead than 30-node in this run), consistent with
measurement noise at microsecond scales rather than a meaningful
trend — reported as measured, not smoothed over.

## Dependency review

Zero new runtime dependencies. `module.py`'s new code imports only
`ragtorch.core.block` (deferred) and `ragtorch.core.composition`
(type-checking only) — both already-existing internal modules.

## Diff review

Scope: `src/ragtorch/core/module.py` (modified: `TYPE_CHECKING`
import additions, `RAGModule.from_graph` classmethod,
`_GraphBackedRAGModule` class), `tests/unit/core/test_ragmodule_architecture.py`
(new, 21 tests), `tests/integration/test_ragmodule_from_graph.py`
(new, 4 tests), `benchmarks/step17_ragmodule_architecture.py` (new).
ADR-021 and requirements matrix A69 were drafted in the prior 17A-17C
phase. No touch to `block.py`, `sequential.py`, `component.py`,
`composition.py`, `connection.py`, `ports.py`, `execution_plan.py`,
`execution.py`, `engine.py`, or `context.py` — confirmed by explicit
`git diff` against every one of them, all showing zero output.

## Known limitations (explicitly named, not silently absorbed)

- **`from_graph` is not promised on arbitrary `RAGModule` subclasses.**
  Only `RAGModule.from_graph(...)` itself is guaranteed — no real
  requirement has demonstrated a need for
  `MyRAG.from_graph(...)`, and answering the resulting constructor/
  state questions speculatively was explicitly rejected (ADR-021 Q3).
- **No plan caching, serialization, or async execution.** Inherited
  as deferred from `Block` (ADR-020), unchanged by this ADR.
- **`_GraphBackedRAGModule` is private and not part of the public
  API** — only `RAGModule.from_graph(...)`'s return value's behavior
  (an actual `RAGModule` instance) is a stable contract; its concrete
  type name is not.
- **Failure-wrap depth grows by one `ExecutionError` layer per
  enclosing `Module`.** This is `Module.__call__`'s existing, correct,
  universal convention — not unique to this ADR — but a caller
  catching only `except ExecutionError:` (not walking `__cause__`)
  will not distinguish which layer actually failed without inspecting
  the chain.

## Decision

**Step 17 implementation Definition of Done: met locally** (Python
3.10 and 3.12 both verified, 431/431, lint/format/mypy clean, `module.py`
99% coverage with only pre-existing uncovered lines). ADR-021's status
remains `Proposed` and A69's evidence remains local-only until real CI
confirms it — per the project's standing rule that local checks are
not CI, and per Steps 13-16's precedent that an ADR is flipped to
`Accepted` only after independent post-merge CI confirmation on the
actual merged `main` SHA.

## Completion record

Pending PR creation (docs-only ADR-021 + A69, then a separate
implementation PR, matching Steps 13-16's exact discipline), PR CI,
merge, and post-merge CI on `main` for both — this section is
completed only after all of those are independently confirmed.
