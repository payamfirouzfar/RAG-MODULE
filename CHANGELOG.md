# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.2.0] - Step 2: Execution, Observability & Evaluation Kernel

### Added

- `ExecutionContext`: immutable execution identity (run_id, optional
  parent_run_id, frozen metadata), with `.child()` for nested executions.
- `Run`: mutable execution-lifecycle record (PENDING/RUNNING/SUCCEEDED/
  FAILED/CANCELLED) with enforced terminal-state transitions.
- `Trace`/`Span`: vendor-neutral hierarchical execution timing, used as a
  context manager via `Trace.start_span()`.
- `MetricsCollector`/`MetricSummary`: named numeric samples summarized into
  count/sum/min/max/p50/p95/p99.
- Structured, context-aware logging (`get_logger`, `log_event`) built on
  Python's standard `logging`, plus `redact()`/`is_sensitive_key()` for
  safe-by-default payload handling.
- `ragtorch.evaluation`: `EvaluationCase`, `Metric` protocol, `ExactMatch`,
  `Latency`, `Evaluator`, `EvaluationResult` — model-agnostic evaluation
  that records git commit and configuration hash for reproducibility.
- Full execution-lifecycle integration test tying Module + ExecutionContext
  + Run + Trace + MetricsCollector + Evaluator together.
- ADR-002 (execution context), ADR-003 (observability architecture),
  ADR-004 (evaluation architecture), ADR-005 (provider independence).
- `docs/architecture/requirements.md`: frozen project-wide requirements
  (R1-R15).
- Step 2 performance baseline and evaluation report.
- CI: evaluation smoke test step.

### Fixed

- `EvaluationResult.git_commit` lookup now cached per-process
  (`functools.lru_cache`) instead of shelling out to `git rev-parse` on
  every `Evaluator.evaluate()` call — cut 100-case evaluation from ~52ms
  to ~134us.

## [0.1.0] - Step 1: Framework Kernel

### Added

- `Module`: base callable component with `forward`/`__call__` separation.
- `RAGModule`: marker base class for top-level RAG systems.
- Automatic child module registration via attribute assignment.
- `named_modules`, `named_children`, `modules`, `children` traversal.
- `Sequential` composition.
- `inspect()` architecture tree and `__repr__`.
- `RAGConfig`: immutable, explicit configuration objects.
- Framework exception hierarchy (`RAGTorchError` and subclasses).
- Lightweight `EventBus`/`Event`/`EventType` observability primitives.
- Unit, integration, and public-API contract tests.
- CI pipeline (format, lint, type check, test, build).
