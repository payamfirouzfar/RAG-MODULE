# ADR-006: Execution Engine

## Context

Step 2 built the individual observability primitives: `ExecutionContext`,
`Run`, `Trace`/`Span`, `MetricsCollector`, structured logging. Nothing yet
coordinates them. Today, producing a fully-observed execution means a
caller manually wiring all five together, as
`tests/integration/test_execution_lifecycle.py`'s
`run_pipeline_with_observability()` helper does. That's fine as a proof
that the primitives compose, but it means every future caller (a `RAGModule`,
a CLI, a server handler) would have to re-derive the same wiring, and any
inconsistency between callers (e.g. one forgets to record a failed-run
metric) becomes a silent gap rather than a framework guarantee.

We need one thing whose job is: *given a module and an input, execute it
and guarantee the full observability contract holds* — every execution
gets a `Run`, a root `Span`, and duration metrics, with no caller able to
opt out of a partial subset by forgetting a step.

## Decision

### Responsibility

Add `ExecutionEngine` (`ragtorch.core.engine`) with one method:

```python
engine.execute(module, input, context=None) -> ExecutionResult
```

Its *only* job is coordinating the existing Step 2 primitives around one
`Module` call. It does not add new execution semantics of its own — it
composes `Run.start()`/`succeed()`/`fail()`, `Trace.start_span()`, and
`MetricsCollector.record()` exactly as the integration-test helper did by
hand, but as a guaranteed, tested contract instead of a convention callers
must remember to follow.

### Why not inside `Module`

`Module.__call__` already exists and already does one thing: it publishes
Step 1's `MODULE_STARTED`/`FINISHED`/`FAILED` events and wraps exceptions
in `ExecutionError`. It deliberately does not know about `Run`, `Trace`, or
`MetricsCollector` — those are Step 2 concepts, and `Module` predates them.
Merging engine responsibilities into `Module` would mean every `Module`
subclass (eventually: every chunker, retriever, router, generator)
inherits execution-management responsibility it never asked for, exactly
the failure mode Step 1's "composition over inheritance" and "small
interfaces" rules exist to prevent. Keeping `ExecutionEngine` separate
preserves the split:

```text
Module           = WHAT computes         (Step 1)
Run              = ONE execution's state  (Step 2)
ExecutionEngine  = HOW an execution runs   (Step 3, this ADR)
```

### Lifecycle

`ExecutionEngine.execute()` drives exactly this sequence, with no
skippable step:

```text
1. context := context or ExecutionContext()
2. run := Run.start(context)
3. span := trace.start_span(module's class name, run_id=context.run_id)
4. try:
       output := module(input)          # Module.__call__, unchanged
       run.succeed(output)
       span.finish(status="ok")
   except Exception as exc:
       run.fail(exc)
       span.finish(status="error")
       re-raise                          # engine does not swallow errors
5. metrics.record(f"{module_name}.duration_s", run.duration)
6. return ExecutionResult(run, trace, metrics)
```

The engine **re-raises** after recording failure state — it does not
swallow exceptions on the caller's behalf, matching `Module.__call__`'s
existing behavior (it also re-raises, wrapped in `ExecutionError`). A
caller that wants to inspect a failed run without a raised exception is
expected to catch it and read `ExecutionResult` from the exception context,
not rely on the engine silently returning a failed result object. This
keeps failure handling honest: "the pipeline raised" is still visible as a
Python exception, not hidden behind an object the caller might not check.

### Context propagation

The engine accepts an optional `ExecutionContext`. If the module being
executed is a composite (`Sequential`, or any future `Module` that calls
child modules internally), context propagation to children is the
composite's responsibility, not the engine's — the engine only manages the
context for the top-level call it was given. A future step may add an
engine-aware `Sequential` variant that calls `context.child()` per step for
per-child run tracking; that is out of scope here. This ADR commits only
to: **the engine does not silently drop or mutate the context it's given.**

### Observability levels

Per the plan, we introduce three levels now, enforced as a single
`ObservabilityLevel` enum on the engine (default `BASIC`):

- `OFF` — no `Trace`/`Metrics` recorded; `Run` is still tracked (status/
  duration are core to "did it work," not optional observability).
- `BASIC` (default) — `Run` + duration metric. No span tree, no structured
  logging.
- `DEBUG` — adds a `Trace` span for the call and a `log_event()` call at
  start/finish.

`FULL` (retrieval candidates, token usage, cost, routing decisions) is
explicitly deferred — those fields don't exist yet (no retriever, no model
adapter), so defining them now would be speculative. Adding a level later
is additive, not a breaking change to this enum.

### Persistence

`ExecutionEngine` does **not** persist anything to disk in this step. The
`RunArtifact` / `.ragtorch/runs/` concept from the plan is real and worth
building, but it's a separate, additive concern (serialization format,
directory layout, opt-in content persistence) that deserves its own ADR
once the in-memory `ExecutionResult` shape has proven itself. Building
persistence before the thing being persisted is stable would risk locking
in a format we'd immediately need to change.

### Performance budget

Established now, to be checked by `evaluation/step3_benchmark.py` and
revisited if real measurements disagree:

- `ExecutionEngine.execute()` at `BASIC` level: **< 50 µs p50** overhead
  over a raw `Module.__call__`.
- At `DEBUG` level (adds one `Trace` span): **< 25 µs p50** additional
  overhead over `BASIC`.

These are initial engineering budgets, not physical constants — Step 2's
own benchmark already showed Run+Trace+Metrics together costing ~8.6 µs
over a bare call, so a 50 µs budget leaves comfortable headroom rather than
being a tight target.

## Alternatives considered

- **Make `Run`/`Trace`/`Metrics` wiring a documented pattern, not a class.**
  Rejected: Step 2's own integration test already had to hand-roll this
  wiring once; every future caller doing so independently is exactly the
  kind of undocumented convention that drifts out of sync across the
  codebase. A single tested `execute()` method is cheaper to maintain than
  N copies of the same try/finally block.
- **Give the engine a "swallow and return a failed result" mode as the
  default.** Rejected as default: it would make `pipeline.run(x)` return
  a result object even when computation didn't actually happen, and a
  caller who forgets to check `result.status` gets silently wrong behavior
  instead of a loud exception. An opt-in non-raising variant may be added
  later behind an explicit flag, but raising stays the default.
- **Build `RunArtifact` persistence in this same step, since the plan asks
  for it.** Deferred, not rejected — see Persistence above. Sequencing it
  after `ExecutionEngine` is proven avoids designing a file format around
  an in-memory shape that hasn't been used yet.

## Consequences

- Every future top-level entry point (a `RAGModule.run()` convenience
  method, a CLI, a server handler) can depend on `ExecutionEngine` instead
  of re-deriving Step 2's wiring, closing the gap the Step 2 integration
  test's manual helper exposed.
- `Module` and `Run` keep their existing, narrow responsibilities;
  `ExecutionEngine` is the only new concept introduced by Step 3.
- The `ObservabilityLevel` enum gives R13 (performance budgets) a concrete
  lever: a latency-sensitive deployment can run at `OFF` or `BASIC` without
  code changes elsewhere.
- Persisted run artifacts remain an open, explicitly deferred piece of
  future work — tracked here so it isn't forgotten, not built prematurely.
