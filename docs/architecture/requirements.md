# Requirements

These are frozen, project-wide requirements — not feature requests for a
particular step. Every future addition to `ragtorch` is checked against
this list before it's considered done. Where a requirement is already
enforced by something concrete (a test, an ADR, a packaging convention),
that's noted so the requirement stays verifiable rather than aspirational.

## R1 — Vendor independence

Core cannot require an LLM provider. See [ADR-005](architecture/decisions/ADR-005-provider-independence.md).

## R2 — Model independence

Any compatible model can be used; the framework does not special-case a
particular vendor's API shape in core.

## R3 — Storage independence

Any supported storage backend (vector DB, lexical index, filesystem) can be
plugged in through an interface defined in core, not hard-coded to one
implementation.

## R4 — Observability independence

No mandatory observability SaaS. Traces, metrics, and logs are usable as
plain local artifacts with no network dependency. See
[ADR-003](architecture/decisions/ADR-003-observability-architecture.md).

## R5 — Evaluation first

Every major feature ships with evaluation, not added retroactively. See
[ADR-004](architecture/decisions/ADR-004-evaluation-architecture.md).

## R6 — Replaceability

Components must be replaceable through interfaces (`Module` subclasses,
`Metric` protocol, and future `Retriever`/`Generator`/`Embedder` protocols).

## R7 — Composability

Small modules compose into larger systems (`Sequential`, nested `Module`
registration) rather than deep inheritance hierarchies. Established in
[ADR-001](architecture/decisions/ADR-001-core-module-abstraction.md).

## R8 — Inspectability

Users can understand the architecture of a running system via
`Module.inspect()` / `Module.__repr__()`, and (once wired to a pipeline)
`Trace.render()` for execution flow.

## R9 — Reproducibility

Runs record enough metadata to reproduce experiments: `ExecutionContext`
carries run identity, `EvaluationResult` records git commit and
configuration hash.

## R10 — Security by default

Sensitive content isn't automatically persisted. Enforced by
`ragtorch.core.logging.redact()` defaulting to redaction, and
`is_sensitive_key()` flagging secret-shaped field names. See SECURITY.md.

## R11 — Optional dependencies

Heavy or vendor-specific dependencies are optional extras
(`ragtorch[ollama]`, `ragtorch[qdrant]`, ...), never part of the default
install. See [ADR-005](architecture/decisions/ADR-005-provider-independence.md).

## R12 — Backward compatibility

Public APIs are explicitly managed: everything re-exported from
`ragtorch.__init__` (or a subpackage's `__init__`) is public; everything
else is internal and may change without notice. Enforced by
`tests/unit/test_public_api.py` as a contract test.

## R13 — Performance budgets

Framework overhead is measured, not assumed. Every step records a
benchmark (`evaluation/benchmark_baseline.py` for Step 1,
`evaluation/step2_benchmark.py` for Step 2) so a future optimization has
real numbers to justify itself against, and so we notice if observability
overhead grows unacceptably relative to raw execution.

## R14 — Local-first

The framework works fully offline, with local models and local storage.
No feature in core or evaluation requires a network call to function.

## R15 — Cloud-optional

Enterprise/cloud capabilities (dashboards, team collaboration, centralized
governance) may be added later as a separate, optional layer — never a
requirement for using the open-source core.
