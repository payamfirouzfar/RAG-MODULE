# Step 14 Evaluation — Step Execution Boundary

Date: 2026-08-16

Branch: `feat/step14-execution-boundary-implementation`, based on
`main` after both docs-only PRs for this step merged and their
post-merge CI was independently confirmed:

- PR #12 (ADR-018 initial contract freeze + requirements matrix A66),
  merged `1e2297a`, post-merge CI run `31969249754`, 329/329 on
  3.10/3.11/3.12.
- PR #13 (ADR-018 `ExecutionResult` → `StepExecutionResult` rename,
  found during the 14E pre-implementation audit), merged `75829ec`,
  post-merge CI run `31969537482`, 329/329 on 3.10/3.11/3.12.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-018, this
evaluation proves: given a valid `ExecutionPlan` and a caller-supplied
`StepHandler`, does `SequentialExecutor.execute` correctly run every
step in order, thread prior results forward through an immutable
snapshot, propagate handler failures unmodified with no partial
result, and remain entirely provider-independent and stateless across
calls — as a static, structural fact, independent of what the handler
actually does or what it resolves a step's work to.

## The two adversarial passes that shaped this implementation

ADR-018 went through more review cycles than any prior ADR before
implementation began, and every cycle found something real:

- **14B adversarial review** (before any code existed) found and fixed
  7 findings against the initial plan-wide design: a BLOCKER-tier
  naming collision (`ExecutionContext` vs. the existing
  `ragtorch.core.context.ExecutionContext`), a BLOCKER-tier
  handler-signature gap (handler received only `node_id`, not the full
  `ExecutionStep`), a retracted false claim (a future async executor
  cannot structurally satisfy a `Protocol` declaring a non-coroutine
  return type), an unacknowledged O(n²) context-construction cost, a
  missing partial-result/node-id-uniqueness policy, an
  implementation-detail statelessness test (`vars(executor)`) replaced
  with a behavioral one, and an imprecise immutability claim (mapping
  vs. value immutability). See ADR-018 "14B adversarial review
  findings" for the full list.
- **14E pre-implementation fresh audit** (after PR #12 already merged
  ADR-018 to `main` as the frozen baseline) found an **eighth**
  collision the first two passes both missed:
  `ragtorch.core.engine.ExecutionResult` already existed (a
  `Run`/`Trace`/`MetricsCollector` bundle, ADR-006), already exported
  bare in both `ragtorch.core.__all__` and `ragtorch.__all__`, and
  pinned by `tests/unit/test_public_api.py`'s export-parity test.
  ADR-018's own results type used the same bare name. Fixed by
  renaming to `StepExecutionResult`, mirroring the
  `StepExecutionContext` precedent exactly, via its own docs-only PR
  (#13) and its own independent post-merge CI confirmation before
  implementation resumed. See ADR-018 "Post-merge finding".

Both naming collisions are now regression-tested directly: the public
API export test (see "API quality" below) checks that the new types
appear only under their `Step`-prefixed names, never as bare
`ExecutionContext`/`ExecutionResult`.

## Contract

```python
@dataclass(frozen=True)
class StepExecutionContext:
    results: Mapping[str, object]


@dataclass(frozen=True)
class StepExecutionResult:
    values: Mapping[str, object]


class StepHandler(Protocol):
    def __call__(self, step: ExecutionStep, context: StepExecutionContext) -> object: ...


class Executor(Protocol):
    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> StepExecutionResult: ...


class SequentialExecutor:
    def execute(self, plan: ExecutionPlan, handler: StepHandler) -> StepExecutionResult: ...
```

`SequentialExecutor.execute` walks `plan.steps` in order, rebuilding a
fresh immutable `StepExecutionContext` snapshot before each step
(never a live view over the internal results dict), and returns a
`StepExecutionResult` only after every step completes successfully. No
`try`/`except` anywhere in `execute` — a handler exception propagates
unmodified, and no partial result is ever constructed. No reference to
`plan`, `context`, or accumulated results is retained after `execute`
returns.

## Correctness

| Invariant | Expected | Result |
| --- | --- | --- |
| Empty plan does not call handler, returns empty result | PASS | PASS |
| Single step | one entry, correct value | PASS |
| Multiple steps | all called | PASS |
| Exact execution order matches `plan.steps` | PASS | PASS |
| Handler receives the full `ExecutionStep`, not only `node_id` | PASS | PASS |
| Later steps see all previously-computed results | PASS | PASS |
| Valid-plan result is exactly complete (no dup/missing) | PASS | PASS |
| Executor relies on, does not revalidate, upstream node-id uniqueness | PASS | PASS |
| Retained context objects reflect a snapshot, not a live view | PASS | PASS |
| Plan is not mutated by execution | PASS | PASS |

```
invariant_count: 10
case_count: 27
error_count: 0
expected_outcome_accuracy: 1.0
```

## API quality

| Property | Result |
| --- | --- |
| `StepExecutionContext.results` mapping is immutable (`TypeError` on write) | PASS |
| `StepExecutionContext` is a snapshot — later mutation of the source dict does not affect an issued context | PASS |
| `StepExecutionResult.values` mapping is immutable | PASS |
| Shallow immutability documented and tested: mutable stored values remain mutable in place | PASS |
| `SequentialExecutor` satisfies the `Executor` `Protocol` structurally | PASS |
| A plain function satisfies the `StepHandler` `Protocol` without inheritance | PASS |
| No naming collision: `StepExecutionContext`/`StepExecutionResult` distinct from `ragtorch.core.context.ExecutionContext`/`ragtorch.core.engine.ExecutionResult` | PASS |

## Functional results

27 new unit tests in `tests/unit/core/test_execution.py`. Combined with
the pre-existing 329, total suite is 356.

| Invariant | Result |
| --- | --- |
| No provider/`Component`/`CompositionGraph`/`ExecutionEngine` import in `execution.py` (AST-based check, reusing the established pattern) | PASS |
| Handler exception propagates out of `execute` unmodified | PASS |
| The exact original exception *object* is preserved (`exc_info.value is error`), not merely its type | PASS |
| Downstream steps do not execute after a failure | PASS |
| No `StepExecutionResult` is ever returned or accessible after a mid-plan failure | PASS |
| Same executor instance is reusable across repeated, sequential `execute` calls without cross-contamination | PASS |
| Sequential-call results match what two independent fresh instances would produce | PASS |

## Test results

```
pytest:        356 passed (329 pre-existing, unmodified + 27 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 26 source files
coverage:      execution.py 100%; overall 99%
```

## Performance

`benchmarks/step14_execution_boundary.py`, Windows, Python 3.12.0,
local. `SequentialExecutor.execute` against a trivial handler
(`lambda step, context: step.node_id`).

| Steps | Total time (s) | Time/step (µs) |
| ---: | ---: | ---: |
| 10 | 0.000013 | 1.27 |
| 100 | 0.000075 | 0.76 |
| 1,000 | 0.001782 | 1.78 |
| 10,000 | 0.145114 | 14.51 |
| 100,000 | 98.833244 | 988.33 |

### Interpretation

This benchmark measures, it does not prove, an asymptotic bound. What
it shows: time-per-step is **not** roughly constant across sizes — it
grew by roughly 780x from the 10-step case to the 100,000-step case,
with the clearest growth appearing between 1,000 and 100,000 steps.
This is consistent with the accepted, documented v0.1 design trade-off
in ADR-018 "Context construction cost": `StepExecutionContext.from_results`
copies the entire accumulated results dict into a fresh
`MappingProxyType` before every step, giving `0 + 1 + ... + (n-1)`
total copy operations across an n-step plan — quadratic in step count,
not linear. The implementation performs a full accumulated-results
copy before each step; these benchmark results show time-per-step
increasing with plan size, consistent with the expected copy cost, not
a proof of an O(n²) bound by other means.

At the 10/100/1,000-step range typical of realistic v0.1 pipelines,
the absolute cost is negligible (under 2ms total even at 1,000 steps).
The cost becomes visible only at the 10,000+ step range, which is far
beyond any composition this framework currently supports building
(`CompositionGraph`/`plan()` have no tested scenario near that size in
this codebase). Per ADR-018's explicit decision, this is not "fixed"
here — a persistent-result-store optimization is deferred to a future,
measurement-informed ADR if a real workload ever demonstrates the cost
matters at a size the framework actually produces.

This benchmark is **not** wired into CI (matching Step 13's own
precedent: `benchmarks/step13_execution_plan.py` is also not part of
`ci.yml`). It is run manually and its results recorded here.

## Compatibility review

| Existing API | Step 14 effect |
| --- | --- |
| `Component` | none — zero lines touched |
| `Module`/`Sequential` | none — zero lines touched |
| `ExecutionEngine`/`ragtorch.core.context.ExecutionContext` | none — zero lines touched |
| `ragtorch.core.engine.ExecutionResult` | none — zero lines touched; new type is `StepExecutionResult`, a distinct name, see "Naming" |
| `CompositionGraph`/`GraphNode`/`Connection` | none — zero lines touched |
| `ExecutionPlan`/`ExecutionStep`/`plan()` | none — zero lines touched; `execution.py` only imports these, does not modify them |
| existing exceptions | unchanged — no new exception type introduced; handler failures propagate as-is, not wrapped |

All 329 pre-existing tests pass **unmodified**.

## Security review

| Question | Answer |
| --- | --- |
| Does `SequentialExecutor.execute` perform any operation with external effect itself? | No — it only calls the caller-supplied `handler`; the handler's behavior is entirely outside this module's control |
| Does it evaluate annotations, use reflection, `eval`, or `exec`? | No |
| Does it import any provider/model dependency? | No — verified by AST-based import inspection (ADV-08) |
| Does it import `Component`, `CompositionGraph`, or `ExecutionEngine`? | No — verified by the same AST-based check |
| Does it automatically log `context.results`/`result.values`? | No — those may contain sensitive, handler-produced data this module knows nothing about |
| Can a `StepExecutionResult` carry a provider client, API key, or open resource? | Possible in principle (values are opaque, handler-produced) — but not introduced or encouraged by this module; no serialization or logging path exists here that would expose it |

## Dependency review

Zero new runtime dependencies. `execution.py` imports
`ragtorch.core.execution_plan` (`ExecutionPlan`, `ExecutionStep`) and
the standard library (`collections.abc`, `dataclasses`, `types`,
`typing`) — no `networkx`, no scheduler package, no persistent-map/
immutable-collections package (per ADR-018's explicit v0.1 decision).

## Diff review

Scope: `src/ragtorch/core/execution.py` (new),
`tests/unit/core/test_execution.py` (new, 27 tests),
`benchmarks/step14_execution_boundary.py` (new), `evaluation/step14-evaluation.md`
(this document). ADR-018 and requirements matrix A66 already merged
via PR #12/#13's separate docs-only review — see those PRs' own
evidence trails. No touch to `Component`, `Module`, `Sequential`,
`ExecutionEngine`, `ragtorch.core.context`, `CompositionGraph`,
`ExecutionPlan`, `execution_plan.py` — confirmed by
`git diff --stat main...HEAD`. Public export path/`__all__` membership
for the new types is decided as part of this implementation PR (see
"Known limitations" below) — not left implicit, per ADR-018
Compatibility.

## Known limitations (explicitly named, not silently absorbed)

- **Synchronous, single-threaded only.** `Executor` cannot be
  satisfied by an `async def execute`; a future async executor is a
  separate, differently-named contract — see ADR-018 Q7.
- **No `ExecutionEngine` integration.** `SequentialExecutor` and
  `ExecutionEngine` remain entirely independent; connecting
  `Run`/`Trace`/`Metrics` to plan-level execution is deferred future
  work.
- **No retries, timeouts, or concurrency.** Explicit non-goals — see
  ADR-018 Non-goals.
- **Quadratic context-construction cost**, measured and accepted for
  v0.1 — see "Performance" above.
- **Shallow immutability only.** `StepExecutionContext.results`/
  `StepExecutionResult.values` are immutable mappings; the objects
  stored as values are not deep-copied or recursively frozen.
- **No node-to-work resolution.** The executor never resolves
  `ExecutionStep` to a `Component` itself — that is entirely the
  caller-supplied `StepHandler`'s responsibility.
- **Thread-safety, reentrancy, and concurrent invocation of the same
  instance are not claimed.** Only sequential reuse is tested and
  guaranteed — see ADR-018 Q9.

## Decision

**Step 14 implementation Definition of Done: met locally** (Python
3.12 verified; 3.10/3.11 verification pending CI, matching the
project's standing discipline of not claiming CI-level confirmation
from local checks alone). Requirements matrix A66's evidence is
updated to reflect this implementation only after real CI confirms it
— per the project's standing rule that an ADR decision is not proof
until implementation/tests/CI independently confirm it.

## Completion record

Pending PR creation, PR CI, merge, and post-merge CI on `main` — this
section is completed only after all of those are independently
confirmed, matching Step 13's exact discipline (see
`evaluation/step13-evaluation.md` "Completion record" for the
template this will follow).
