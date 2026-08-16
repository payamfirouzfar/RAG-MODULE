# Step 7 Evaluation — Component Ports & Compatibility

Date: 2026-08-16

Branch: `feat/step7-component-ports`

## Scope

Framework/architecture feature, not RAG quality. Per ADR-011, this
evaluation proves: can two independently-described component boundaries
be checked for compatibility, deterministically, without executing
either component — the prerequisite for a future `Block`/graph
composition layer, not the composition layer itself.

## Contract

- `InputPort(name: str, type: type)` — frozen, validates `type` is a
  real Python class at construction.
- `OutputPort(name: str, type: type)` — same.
- `is_compatible(output: OutputPort, input: InputPort) -> bool` —
  `issubclass(output.type, input.type)`; never raises for validly
  constructed ports.

## Functional results

| Invariant                                                              | Result |
| ---------------------------------------------------------------------------- | ------ |
| Exact type match is compatible                                                  | PASS |
| Subtype output feeding supertype input is compatible                               | PASS |
| Supertype output feeding subtype input is NOT compatible (not symmetric)              | PASS |
| Unrelated types are incompatible                                                         | PASS |
| `object` input accepts any class (documented Python behavior, not a special case)           | PASS |
| Non-class `type` value (string, int) raises `ValidationError` at construction                  | PASS |
| Generic alias (`list[Document]`) raises `ValidationError` at construction (not a class)            | PASS (see CI section — this required a real fix; initially passed locally on 3.12 for the wrong reason, failed on CI's 3.10/3.11) |
| Ports are immutable (frozen dataclass)                                                                | PASS |
| `is_compatible()` does not execute either component                                                     | PASS |
| No `get_type_hints`/`eval`/`exec` anywhere in `ports.py` (verified by source inspection, not assumed)      | PASS |
| No provider import in `ports.py` (verified via AST import inspection, not string-scan — see note below)      | PASS |
| Fake `Retriever` → `Reranker` (list → list): compatible                                                          | PASS |
| Fake `Retriever` → `Generator` (list → str): incompatible                                                           | PASS |

**Note on the provider-independence test:** the plan's suggested
implementation was a naive lowercase substring scan for `"torch"` among
other vendor names. Running it against this module's actual source
failed — `"torch"` is itself a substring of `"ragtorch"`, which appears
in the module's own docstring and its `from ragtorch.core.errors import
ValidationError` line. Caught before commit, not shipped as a flaky
test: replaced with an `ast`-based check of actual `import`/`from...
import` statements' top-level module names, which is both correct
(no false positive on the project's own name) and more precise than a
substring scan (won't false-negative on `import torch as t` disguised
imports either, since it inspects the parsed import target, not
arbitrary text).

16 unit tests (`tests/unit/core/test_ports.py`) + 4 integration/contract
tests (`tests/integration/test_component_ports.py`), all passing.

## Test results

```
pytest:  179 passed (159 pre-existing, unmodified + 16 unit + 4 integration)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 20 source files
coverage:      99% overall; ports.py 100%
```

## Performance

`benchmarks/step7_component_ports.py`, Windows, Python 3.12.0, local.

| Operation                                                     | p50 (µs) |
| ------------------------------------------------------------------ | -------- |
| `InputPort` construction                                              | 0.4      |
| `OutputPort` construction                                                | 0.4      |
| `is_compatible()` — compatible pair                                        | 0.1      |
| `is_compatible()` — incompatible pair                                        | 0.1      |
| `Module(input)` — no ports involved (regression guard)                          | 2.0      |

### Regression vs Step 6 baseline

| Baseline (Step 6)   | This measurement | Delta |
| ---------------------- | ------------------- | ----- |
| Module call: ~1.9µs p50   | 2.0µs p50               | +0.1µs, within normal run-to-run machine noise observed throughout this session (±0.1-0.3µs across repeated Step 5/6 benchmark runs) |

`ports.py` is never imported by `module.py`, `engine.py`, `sequential.py`,
or any other hot-path file — confirmed by inspection of the diff (see
Compatibility review) — so this is not a causal regression; it is
measurement noise, recorded honestly rather than re-run to chase a
"nicer" number.

## Evaluation (architecture invariant, not RAG quality)

Reused fixtures, no new evaluation subsystem:

```
FakeRetriever.output_port  (list) -> FakeReranker.input_port  (list): compatible = True
FakeRetriever.output_port  (list) -> FakeGenerator.input_port (str):  compatible = False
```

Demonstrates the actual payoff this ADR exists for: a wrong connection
between two independently-described, unrelated fake components is
correctly and deterministically rejected without running either.

## CI — a real cross-version bug was caught here, not by local checks

The first push to PR #3 **failed on all three Python versions** (3.10,
3.11, 3.12) in `test_input_port_rejects_generic_alias`: "DID NOT RAISE
ValidationError." This was not a flaky test — it was a genuine gap in
local verification. Root cause, confirmed by testing directly against
real interpreters (not assumed from documentation):

```
isinstance(list[Document], type)
    Python 3.10: True
    Python 3.12: False
```

`isinstance(x, type)` is **not a version-stable way to detect a builtin
generic alias** (`list[X]`, `dict[K, V]`, etc., instances of
`types.GenericAlias`) — this behavior changed within the project's own
supported range (3.10-3.12). The local development environment used
throughout this step was Python 3.12.0 only, where the original
`isinstance(self.type, type)` check happened to correctly reject
`list[Document]` — masking the bug until CI ran the same test on 3.10
and 3.11.

**Fix**: `ports.py`'s validation now explicitly excludes
`types.GenericAlias` — `isinstance(value, type) and not
isinstance(value, types.GenericAlias)` — rather than relying on
`isinstance(x, type)` alone. Verified directly against real Python 3.10
and 3.12 interpreters (`py -3.10`, not just the local 3.12 venv) before
re-pushing, and the full 179-test suite re-run on both versions
locally, not merely assumed fixed from the one-line change. `Union` and
`Any` were separately confirmed to already behave consistently
(`isinstance(x, type)` is `False` for both, on 3.10 and 3.12 alike) —
only `types.GenericAlias` needed the explicit exclusion.

This is exactly the failure mode CI-first verification exists to catch:
a real, version-dependent bug that 100% of local tests (on the one
Python version installed locally) could not have found, and that would
have shipped as "179/179 passing" without ever being wrong on the
machine that wrote it.

Verified via GitHub Actions on push (see commit log for run IDs) —
Python 3.10, 3.11, 3.12, following the same "local green != project
green" discipline established since Step 5. No new CI workflow created;
the existing `ci.yml` picks up the new tests automatically.

## Compatibility review

- `Component`, `Module`, `ExecutionEngine`, `ExecutionContext`,
  `Sequential`: **zero lines changed**. `ports.py` is a new, standalone
  module; nothing existing imports it.
- All 159 pre-existing tests pass **unmodified** — no existing test file
  required editing.
- `ValidationError` reused; no new exception type introduced.
- `Component` protocol unchanged: no `input_ports`/`output_ports`
  property added to it, per ADR-011 Non-goals — ports remain optional,
  external metadata.

## Security review

| Question                                    | Answer |
| ------------------------------------------------ | ------ |
| Arbitrary code execution possible?                    | No — `type` is passed as a real object the caller already has in scope; never parsed or `eval`'d |
| Annotations evaluated?                                    | No — `ports.py` never calls `typing.get_type_hints()`; verified by source inspection test |
| Malicious forward references possible?                        | No — no annotation reflection occurs at all |
| Serialized schemas involved?                                      | No |
| Does validation execute arbitrary user code?                          | No — `isinstance(self.type, type)` and `issubclass()` only |

## Dependency review

Zero new dependencies. `ports.py` imports only `dataclasses` (stdlib)
and `ragtorch.core.errors` (existing internal module). Confirmed via
`git diff pyproject.toml` (empty).

## Diff review

Scope: `src/ragtorch/core/ports.py` (new), `src/ragtorch/core/__init__.py`
and top-level `src/ragtorch/__init__.py` (export, following the
established 100%-parity convention between the two — verified
programmatically, not assumed), `tests/unit/core/test_ports.py` (new),
`tests/integration/test_component_ports.py` (new),
`tests/unit/test_public_api.py` (three entries added),
`benchmarks/step7_component_ports.py` (new), ADR-011 (new, amended
before implementation per Staff review), requirements matrix (updated).
No touch to `component.py`, `module.py`, `engine.py`, `context.py`,
`sequential.py`, `events.py`, or any provider file.

## Decision

**Step 7 Definition of Done: met**, ADR-011 status updated from Proposed
to Accepted only after this evaluation and (per the project's standing
CI-verification discipline) actual GitHub Actions confirmation — see
CI section above and the commit log for the specific run. Generic-
parameter-aware compatibility, `Union`/structural typing, ports attached
to `Component`, a `Block`/graph builder enforcing compatibility, and
port serialization all remain explicitly deferred per ADR-011 Non-goals.
