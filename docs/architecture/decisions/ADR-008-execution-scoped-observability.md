# ADR-008: Execution-Scoped Observability

## Status

Accepted for Step 5 implementation.

## Context

Step 4 introduced explicit `ExecutionContext` propagation through nested modules. The context carries run identity and parent-child identity, but the current module lifecycle event system uses a process-wide `EventBus`, and events contain only `module_name` plus a payload. A concurrent or nested execution can therefore emit indistinguishable lifecycle events.

The framework must not solve this by introducing a global current context. That would violate the explicit execution-identity design established by ADR-002 and ADR-007.

## Decision

Observability events remain lightweight and synchronous, but execution identity becomes explicit event data.

When a module is called with an `ExecutionContext`, lifecycle events include that context's `run_id` and relevant parent identity. When no context is supplied, the event remains valid and has no fabricated execution identity.

The long-term design is execution-scoped event emission rather than hidden global execution state. The existing process-wide bus may remain as a compatibility subscription mechanism temporarily, but the event data itself must be sufficient to correlate a run without relying on mutable global state.

## Event identity

The semantic event envelope is conceptually:

```text
Event
  type
  module_name
  timestamp
  run_id?
  parent_run_id?
  payload
```

`run_id` and `parent_run_id` are correlation metadata, not business data.

## Invariants

- Events from sibling executions are distinguishable.
- Nested events preserve parent-child identity.
- No event listener can mutate execution context.
- No thread-local or contextvar is required for correctness.
- Direct `module(input)` remains backward compatible.
- Existing subscribers continue receiving lifecycle events.
- Observability failure must not become business-logic failure unless an explicit future policy says otherwise.

## Alternatives rejected

### Global current context

Rejected because concurrent executions could overwrite shared state and because implicit propagation makes execution semantics harder to reason about.

### Put the full ExecutionContext in every event

Rejected because events should carry correlation metadata, not become a second transport for arbitrary execution state.

### Remove the global EventBus immediately

Rejected for this migration step because the event bus is already part of the internal behavior and tests. We first make event identity correct, then later decide whether event delivery should become per-engine/per-execution.

## Consequences

- Traces, logs, metrics, and events can be correlated by run ID.
- Future provider routing and fallback decisions can be observed without inventing another identity system.
- The current `Module` API remains compatible.
- A later runtime redesign can make event delivery execution-scoped without changing the semantic event contract.
