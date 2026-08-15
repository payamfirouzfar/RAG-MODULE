# ADR-002: Execution Context

## Context

Step 1's `Module.__call__` already publishes `MODULE_STARTED`/`FINISHED`/
`FAILED` events through a process-wide `EventBus`. That's fine for a single
synchronous call chain, but nothing ties those events together as "the same
execution," and nothing distinguishes "the retriever step of request A" from
"the retriever step of request B" once a server is handling many requests
concurrently. Logs, traces, metrics, and evaluation artifacts all need a
shared way to answer: *which execution produced this?*

## Decision

Introduce `ExecutionContext`: a small, frozen dataclass carrying a `run_id`,
an optional `parent_run_id`, and immutable `metadata`. It is not a service
or a registry — it is a value object, passed explicitly to whatever needs
it (a `Run`, a log call, a trace span), never looked up from global state.

`ExecutionContext.child(**metadata)` creates a new context for a nested
execution (e.g. a retrieval call inside a larger RAG run), recording the
parent's `run_id` as `parent_run_id` and merging metadata. This gives us a
parent/child chain without a central registry tracking "current" context.

## Alternatives considered

- **Global "current run" state** (e.g. a module-level variable or
  contextvar holding "the active run"). Rejected as the default: it works
  for simple synchronous scripts but actively breaks under concurrent
  requests, async execution, and testing — exactly the failure mode Step 1's
  "no global mutable state" rule exists to prevent. A contextvar-based
  convenience wrapper may be added later as sugar on top of explicit
  passing, but explicit passing must remain the primitive.
- **Put identity fields directly on Module.** Rejected: Module describes
  *what* computes, not *one execution* of it — see ADR (Run vs Module,
  documented alongside `run.py`). A single Module instance must be
  callable many times, each with its own execution identity.

## Consequences

- Every later observability primitive (`Run`, `Trace`, structured logging)
  takes an optional `ExecutionContext` rather than inventing its own
  identity scheme.
- Concurrent/async execution is not precluded by the design — nothing here
  assumes one execution at a time.
- Callers that don't care about correlation can omit the context entirely
  (`Run.start()` creates a default one), so the feature has no forced cost
  for simple use.
