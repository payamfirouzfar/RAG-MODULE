# ADR-009: Benchmark and Evaluation Artifact Locations

## Status

Accepted

## Context

Steps 1-4 placed framework microbenchmarks (`*_benchmark.py`) and their
accompanying reports (`*-evaluation.md`) together under `evaluation/`,
alongside `ragtorch.evaluation`'s own smoke-test usage. Step 5 introduced a
second location, `benchmarks/`, for `step5_event_context_overhead.py`,
without an ADR governing the split. The repository currently has two
directories serving what reads as the same purpose — "measure something
about the framework and record it" — with no documented rule for which new
files go where. Left unresolved, Step 6 (and every step after it) has no
principled place to put its own benchmark, and the inconsistency compounds.

The two concerns being conflated are actually distinct:

- **Framework/runtime performance**: "how many microseconds does
  `Module.__call__` cost?" — a question about the engineering artifact
  itself, answerable without any RAG-specific concept (no query, no
  document, no model).
- **System/RAG quality evaluation**: "how good are this retriever's
  results?" — a question about behavior *of a configured system*, per
  ADR-004's `EvaluationCase`/`Metric`/`Evaluator`/`EvaluationResult`
  machinery, which doesn't exist for framework microbenchmarks and
  shouldn't be forced onto them.

`ragtorch.evaluation` (the Python package, ADR-004) already exists and is
explicitly about the second concern — provider-agnostic but
system-behavior-agnostic quality measurement. The `evaluation/` *directory*
(a repo-root location for step reports and scripts) has drifted to also
hold framework microbenchmarks, which is a naming collision between two
different things that happen to share the word "evaluation."

## Decision

Two separate repo-root directories, split by what is being measured, not
by which step introduced the file:

- **`benchmarks/`** — framework/runtime performance measurements. Timing
  of `Module`, `Sequential`, `ExecutionEngine`, `Component`, event
  overhead, or any other pure-engineering hot-path question. No RAG
  concepts (queries, documents, retrieval, generation) belong here,
  because none exist yet and won't for several more steps.
- **`evaluation/`** — system/RAG-quality evaluation artifacts: datasets,
  `Metric` implementations, evaluation reports, and (once real components
  exist) recall/faithfulness/cost/latency-of-a-configured-pipeline
  results. This is the directory `ragtorch.evaluation` (the package)
  conceptually belongs under, once there's something worth evaluating
  beyond framework smoke tests.

This ADR does **not** move any existing file.
`evaluation/benchmark_baseline.py`, `evaluation/step1-evaluation.md`
through `step4-evaluation.md`, and `evaluation/step2_benchmark.py` through
`step4_benchmark.py` all predate this decision and remain in place —
reclassifying and moving eight files is a separate, explicit migration
that should be its own reviewed change if and when it happens, not a
silent side effect of a Step 6 ADR. Step 6's own benchmark
(`step6_component_overhead.py`) and its report (`step6-evaluation.md` or
equivalent) are the first artifacts placed under this rule going forward.

### Going forward

- New framework/runtime microbenchmarks → `benchmarks/step<N>_<name>.py`.
- New RAG/system-quality evaluation artifacts → `evaluation/`.
- Step evaluation *reports* (the markdown scorecards like
  `step4-evaluation.md`) are a hybrid — they report on both framework
  quality gates (tests, mypy, coverage) and, when a benchmark exists, its
  numbers. These continue to live in `evaluation/` as the step-level
  narrative record, referencing the relevant `benchmarks/stepN_*.py`
  script by path, rather than duplicating benchmark code inline.

## Non-goals

- Moving or renaming any existing file in this step.
- Introducing subdirectories (`benchmarks/baseline/`,
  `evaluation/datasets/`, `evaluation/metrics/`) before there's a
  concrete second file that needs one. One file per new concept is not
  yet evidence a subdirectory is warranted.
- Deciding CI's benchmark-regression-gate methodology (warmup, iteration
  count, statistical threshold) — that's Step 6's own benchmark-protocol
  work, not a directory-naming question.

## Alternatives considered

- **Single `benchmarks/` directory for everything, folding in RAG
  evaluation too.** Rejected: conflates two questions ("is the framework
  fast" vs. "is this pipeline good") that will diverge further once real
  evaluation datasets and multi-metric reports exist — exactly the
  ADR-003 reasoning already applied to keep logging/tracing/metrics/
  evaluation as four separate primitives, extended to their file-level
  home.
- **Retroactively migrate all eight existing
  `evaluation/*_benchmark.py`/`*-evaluation.md` files now.** Rejected for
  this ADR: out of scope for Step 6, and doing it as a drive-by inside a
  Component-contract step would make that diff harder to review for its
  actual purpose.
- **No rule; let each step's author choose.** Rejected: this is exactly
  the ambiguity that produced the current split with no documented
  reasoning — the next step (and the one after) would face the identical
  unresolved question.

## Consequences

- Step 6's benchmark has an unambiguous home:
  `benchmarks/step6_component_overhead.py`.
- `evaluation/` is reserved for its ADR-004 purpose going forward,
  without pretending the eight pre-existing files there are wrongly
  placed enough to justify a scope-creeping move right now.
- A future, explicitly-scoped migration ADR/PR can relocate the Step 1-4
  files if and when that's judged worth the diff noise — this ADR makes
  that an intentional future decision, not a silent inconsistency nobody
  chose.
