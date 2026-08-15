# Step 5 Performance Baseline: Event Context Overhead

## Purpose

Verify that adding execution identity to lifecycle events does not impose an unnecessary cost on the common `module(input)` path.

This is a framework-level benchmark. It is intentionally separate from RAG quality evaluation because it measures runtime overhead rather than retrieval or generation quality.

## Pre-fix observation

A head-to-head 50,000-sample measurement supplied during Step 5 review reported:

| Revision | Plain `module(1)` p50 |
|---|---:|
| `main` | 1.6 µs |
| Step 5 before optimization | 2.4 µs |

Observed change: approximately **+50%**.

The identified cause was unconditional construction of the `event_kwargs` dictionary in `Module.__call__`, even when no `ExecutionContext` was supplied.

## Step 5 correction

The no-context and context-aware execution paths are now explicit. The no-context path constructs events without execution-identity fields, while the context path attaches `run_id` and `parent_run_id`.

This preserves the semantic contract while removing the avoidable dictionary construction from the common path.

## Measurement protocol

Run:

```bash
python benchmarks/step5_event_context_overhead.py
```

The benchmark uses 50,000 timed samples after a warm-up and reports p50/p95 for:

- execution without `ExecutionContext`;
- execution with `ExecutionContext`.

GitHub Actions runs the benchmark for every supported Python version and uploads the output as an artifact. This makes the current post-fix measurement auditable instead of relying on a hand-written number.

## Interpretation rule

Do not compare microsecond values across different machines as if they were absolute truths. For regression analysis, compare measurements produced by the same CI environment and Python version, or by a controlled benchmark environment.

The Step 5 merge gate is therefore:

1. formatting passes;
2. lint passes;
3. strict mypy passes;
4. all tests pass;
5. the benchmark executes successfully and produces an artifact;
6. the post-fix benchmark output is reviewed against the pre-fix observation.

A hard numeric threshold will only be introduced after a stable CI baseline has been collected. This avoids creating an arbitrary microbenchmark budget that is sensitive to runner noise.
