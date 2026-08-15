# ADR-003: Observability Architecture

## Context

"Observability" is not one thing. A developer debugging a slow RAG pipeline
needs to ask different questions that a single log stream cannot answer
well:

- *What happened?* → a log line: "Retriever failed to connect to database."
- *How long did it take, and where?* → a trace: `RAG > Retriever > VectorSearch`.
- *How much, numerically?* → a metric: `retrieval_latency_ms = 42`.
- *Was it correct?* → an evaluation: `recall@5 = 0.91`.

Conflating these (e.g. trying to derive timing from log timestamps, or
quality from log content) produces a system that's mediocre at all four
instead of good at each.

## Decision

Keep four separate, purpose-built primitives, each usable independently:

- **Logging** (`ragtorch.core.logging`): freeform, human-readable events,
  built directly on Python's standard `logging` module so a host
  application configures handlers/levels itself, per Python's own guidance
  for library code. `log_event()` attaches `run_id`/`parent_run_id` from an
  `ExecutionContext` as structured `extra` fields when one is available,
  so log lines can be correlated with traces after the fact — but logging
  works with no context at all.
- **Tracing** (`ragtorch.core.trace`): a vendor-neutral `Trace`/`Span` tree
  recording hierarchical timing. No OpenTelemetry dependency in core;
  exporting a `Trace` to OpenTelemetry (or any other backend) is an adapter
  built later, not a requirement of using tracing today.
- **Metrics** (`ragtorch.core.metrics`): named numeric samples
  (`MetricsCollector.record`/`increment`), summarized into
  count/sum/min/max/p50/p95/p99 on demand — the same shape as Step 1's
  standalone performance-baseline script, now usable at runtime.
- **Evaluation** (`ragtorch.evaluation`): a separate concern entirely (see
  ADR-004) — not folded into "observability" because it answers a
  fundamentally different question (correctness/quality vs. what happened).

None of these four write to global mutable state; all are instantiated and
passed explicitly (consistent with ADR-002 and Step 1's "no global mutable
state" rule).

## Safety rule

Only metadata is captured by default. Logging must never emit raw prompts,
documents, retrieved content, or secrets. `redact()` in
`ragtorch.core.logging` enforces this at the API level: a value passed to
it is replaced with `<redacted Type len=N>` unless the caller explicitly
passes `allow=True`, so accidentally logging a payload requires an explicit
opt-in mistake rather than an accidental default. `is_sensitive_key()`
flags field names that look like secrets (`api_key`, `authorization`,
`password`, ...) so future callers (e.g. a config dumper) can apply the
same rule to arbitrary key/value data.

## Alternatives considered

- **A single unified "Observability" object bundling logs+traces+metrics.**
  Rejected: it would force every caller to depend on all three even when
  they need one, and it blurs a distinction (log vs. trace vs. metric)
  that's genuinely useful to keep sharp.
- **Adopt OpenTelemetry directly in core.** Rejected for now: it would add
  a real dependency to a core we've committed to keeping dependency-free,
  and would tie our internal representation to OTel's data model before we
  know we need to. An OTel exporter is a natural, optional addition later.

## Consequences

- A user who wants only structured logs, without tracing or metrics, pays
  no cost for the parts they don't use.
- Local-first observability is possible without any of the four: metrics
  and traces are plain Python objects a user can serialize to files
  themselves; no server or SaaS is required to get value from them.
- Exporting to a vendor (OpenTelemetry, Datadog, etc.) becomes a translation
  layer from our internal representation, not a hard dependency of using
  the framework.
