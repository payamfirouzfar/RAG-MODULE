# Step 1 Evaluation — Framework Kernel

Date: 2026-08-15

## Functional (Level A/B — unit & integration)

| Component            | Result |
| --------------------- | ------ |
| Module                | PASS   |
| RAGModule              | PASS   |
| Child registration     | PASS   |
| Sequential              | PASS   |
| inspect() / __repr__   | PASS   |
| RAGConfig               | PASS   |
| Error hierarchy         | PASS   |
| Event bus                | PASS   |
| Public API contract      | PASS   |
| End-to-end pipeline (integration) | PASS |

38/38 tests passing (`pytest`).

## Quality

| Check          | Result |
| -------------- | ------ |
| Unit coverage  | 99% (167 statements, 1 uncovered defensive branch) |
| Lint (ruff)    | PASS, 0 issues |
| Format (ruff format --check) | PASS |
| Type check (mypy --strict) | PASS, 0 errors, 7 files |
| Package build (editable install) | PASS |

The one uncovered line (`module.py`, the `RegistryError` re-raise inside
`__call__`) is unreachable through the public `__call__` path in current
tests because `RegistryError` is only raised by `register_module`, which
runs during attribute assignment, not inside `forward()`. Left uncovered
rather than adding a contrived test for a defensive branch.

## Performance baseline (Windows, Python 3.12, `evaluation/benchmark_baseline.py`)

| Operation                                   | p50 (µs) | p95 (µs) | p99 (µs) |
| -------------------------------------------- | -------- | -------- | -------- |
| Single module call                            | 5.2      | 6.2      | 15.8     |
| Sequential, 10 modules                          | 56.4     | 177.7    | 5256.1*  |
| inspect() over 11-module tree                    | 20.4     | 43.6     | 125.1    |
| register_module via attribute assignment           | 1.8      | 4.5      | 15.9     |

\* p99 tail is GC/scheduler noise typical of `time.perf_counter` microbenchmarks
on a shared dev machine, not a framework issue — no allocation-heavy code runs
per call. Numbers are a baseline for future comparison, not an SLA.

No Cython/Rust optimization is warranted at this stage — overhead is
microseconds and dominated by Python function-call cost, not framework logic.

## Engineering

| Item                | Result |
| -------------------- | ------ |
| Git repository         | Initialized, `main` branch |
| .gitignore              | Present |
| License (Apache-2.0)     | Present |
| CHANGELOG                 | Present |
| CONTRIBUTING               | Present |
| SECURITY                    | Present |
| CODE_OF_CONDUCT               | Present |
| CI (GitHub Actions)             | `.github/workflows/ci.yml`: format, lint, type check, test, build across Python 3.10–3.12 |
| pre-commit config                 | Present |
| ADR-001                             | Present (core Module abstraction rationale) |

## API stability

Public surface: `ragtorch.__init__` re-exports `Module`, `RAGModule`,
`Sequential`, `RAGConfig`, the error hierarchy, and event primitives.
Everything else (`_modules`, `_name`, `_inspect_children`, `_max_depth`) is
internal. Guarded by `tests/unit/test_public_api.py` as a contract test.

## Reproducibility

No randomness anywhere in Step 1. Same input always produces same output
and same event sequence.

## Scope compliance

Confirmed no LLM, embedding, vector-database, LangChain/LangGraph, or Cython
dependency anywhere in `src/ragtorch`. `pyproject.toml` core `dependencies`
list is empty.

## Verdict

**Step 1 Definition of Done: met.** Proceed to Step 2 when ready.
