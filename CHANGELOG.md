# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/). This
project adheres to [Semantic Versioning](https://semver.org/), with the
pre-1.0 qualification made explicit in
[ADR-024](docs/architecture/decisions/ADR-024-versioning-and-release-policy.md):
while `MAJOR` is `0`, a `MINOR` bump may include breaking changes to the
public API (`ragtorch.__all__`); `PATCH` bumps are backward-compatible
fixes only.

## [0.5.0] - Step 28: Public Python Package / PyPI Release Infrastructure

### Added

- `docs/RELEASING.md`: the deterministic release procedure (version
  bump → CHANGELOG → local validation → PR → CI → merge → tag →
  automated build/validate/publish/verify) — see ADR-024.
- ADR-024: versioning and release policy, making SemVer's pre-1.0
  allowance explicit and documenting why `pyproject.toml`'s manually-set
  `version` field (not dynamic/VCS-derived versioning) remains the
  single source of truth.
- `.github/workflows/release.yml`: a dedicated release workflow,
  deliberately separate from `ci.yml`. Triggered only by a `v*` tag push
  or an explicit manual confirmation — never by a pull request or a
  plain push to `main`. Rebuilds and independently re-validates the
  wheel/sdist from the tagged commit (including verifying the tag
  matches `pyproject.toml`'s version exactly), publishes via PyPI
  Trusted Publishing (OIDC — no stored API token), then verifies the
  publication by installing the just-published version from PyPI itself
  into a fresh environment and running a smoke test.
- Two new packaging tests (`tests/packaging/test_clean_install.py`):
  `ExecutionEngine` and the evaluation API (`ragtorch.evaluation`) are
  now actually executed — not merely imported — against a clean
  installed wheel, closing a real coverage gap the prior test suite had
  (only `Module`/`Sequential` were functionally exercised).
- `benchmarks/step28_packaging_properties.py`: wheel/sdist build time,
  clean-install time, import time, and artifact size, measured (not
  asserted against a threshold) for regression visibility.
- `pyproject.toml`: added `keywords`, refined `classifiers`
  (`Development Status :: 3 - Alpha`, `Operating System :: OS
  Independent`, `Typing :: Typed`), and added `Repository`/`Issues`/
  `Changelog` project URLs alongside the existing `Homepage`.

### Changed

- README rewritten to accurately describe the current state (previously
  stuck at "Step 4" wording from early in the project) with explicit
  "what ragtorch is today" / "what ragtorch is not yet" sections, so the
  package is never marketed as shipping RAG-provider functionality it
  does not have.
- **PyPI distribution name changed to `ragmodel`** (`pyproject.toml`'s
  `name` field). `pip install ragmodel`, then `import ragtorch` in code
  — the Python import name is unchanged and remains `ragtorch`
  everywhere (PyPI allows the distribution name and import name to
  differ; this is a metadata-only change with zero source code impact).
  Decided and requested by the repository owner before the PyPI
  Trusted Publisher was registered, so the pending publisher on PyPI
  was configured directly under the `ragmodel` project name.

### Compatibility

- Zero changes to the public API (`ragtorch.__all__`) or any existing
  `Module`/`Sequential`/`Block`/`CompositionGraph`/`ExecutionEngine`/
  evaluation behavior. This release is packaging/release-infrastructure
  only.

### Published

- **`ragmodel` 0.5.0 is published on PyPI**: https://pypi.org/project/ragmodel/.
  Publication run: `release.yml` run
  [32114922290](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32114922290)
  (triggered by tag `v0.5.0`), `publish` job succeeded, gated behind the
  `pypi` GitHub Environment's required-reviewer approval. Verified
  independently by installing `ragmodel==0.5.0` from the real PyPI index
  into a fresh, isolated virtual environment (outside any source
  checkout) and running a full smoke test: version (`0.5.0`) and install
  path (`site-packages`, not the repo) both correct; a `Retriever` →
  `Generator` `Sequential` pipeline; `ExecutionEngine` with `DEBUG`
  observability (`RunStatus.SUCCEEDED`, rendered trace); the evaluation
  API (`Evaluator`/`ExactMatch`, `mean('exact_match') == 1.0`); and
  `RAGConfig` — all executed successfully against the published
  artifact, not a local build. GitHub release:
  https://github.com/payamfirouzfar/RAG-MODULE/releases/tag/v0.5.0
  (created separately from the `v0.5.0` tag after a real, diagnosed CI
  permissions bug — see `evaluation/step28-evaluation.md`'s publication
  section for the full incident record — prevented the workflow's own
  automated release-creation step from succeeding on the first run;
  the underlying `contents: write` permission gap was fixed in
  `release.yml` for all future releases).

## [0.4.0] - Step 4: Runtime Context Propagation + Module Execution Semantics

### Added

- `Module.__call__`/`forward` gain an optional keyword-only `context`
  parameter. Whether a subclass's `forward()` receives it is detected once
  per class (cached, via `inspect.signature`) rather than requiring every
  subclass to opt in — existing `forward(self, input)` subclasses from
  Steps 1-3 are unaffected.
- `Sequential.forward` derives a distinct `context.child(step=...)` per
  step when a context is given, so nested children get correctly-parented,
  mutually-isolated execution identities instead of sharing one context or
  receiving none.
- `ExecutionEngine.execute()` now threads its `ExecutionContext` into the
  top-level module call it runs, closing the gap Step 3's ADR-006
  explicitly deferred ("context propagation to children is the
  composite's responsibility, not the engine's").
- ADR-007: nested module execution semantics — invariants (backward
  compatibility, no global state, parent/child identity, explicit failure
  propagation, bounded signature-detection cost) and explicit non-goals
  (automatic nested trace spans/metrics, DAG scheduling, persistence —
  deferred to later steps).
- Step 4 performance baseline: context-propagation overhead per
  `Sequential` step measured and a regression budget (< 50 µs p50) frozen
  from real numbers.

### Compatibility

- All 125 Step 1-3 tests pass unmodified — no existing test file required
  editing. `module(input)` with no context behaves identically to before.

## [0.3.0] - Step 3: Execution Engine + Module Lifecycle + Observability Contract

### Added

- `ExecutionEngine`: coordinates `Run`/`Trace`/`MetricsCollector` around a
  single `Module` call as a guaranteed contract instead of a convention
  every caller must re-derive (ADR-006).
- `ObservabilityLevel`: `OFF` (Run only), `BASIC` (default; adds a
  duration metric), `DEBUG` (adds a trace span and start/finish/failure
  structured log events). `FULL` explicitly deferred until
  retrieval/generation components exist to populate it.
- `ExecutionResult`: the `run`/`trace`/`metrics` produced by one
  `engine.execute()` call, with an `.output` convenience property.
- Integration tests: engine executing a `Sequential` composite pipeline
  end-to-end (success and failure paths), and `Evaluator` scoring a system
  driven through `ExecutionEngine.execute()`.
- ADR-006: execution engine responsibility, lifecycle, error semantics,
  context-propagation scope, observability levels, and performance
  budgets — plus why `RunArtifact` persistence is deferred to its own
  future ADR rather than built prematurely.
- Step 3 performance baseline, checked against the ADR-006 budgets (both
  passed with wide margin).

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
