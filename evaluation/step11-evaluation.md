# Step 11 Evaluation — Connection Identity and Directionality

Date: 2026-08-16

Branch: `feat/step11-connections`, based on `main` after PR #5 (Step 10)
was merged with explicit approval.

## Scope

Framework/architecture feature, not RAG quality. Per ADR-015, this
evaluation proves: does `Connection` correctly persist a single,
directed, validated data-flow edge as data — something
`check_connection()` (Step 10) deliberately never did, since it only
checks a proposed pairing in the moment and forgets the answer — while
delegating all compatibility logic to the existing `check_connection()`
rather than duplicating it, and without accidentally introducing any
fan-out/fan-in cardinality rule nobody decided on.

## Contract

```python
@dataclass(frozen=True)
class Connection:
    source_node_id: str
    source_port: OutputPort
    target_node_id: str
    target_port: InputPort
```

`__post_init__` enforces, in order: non-empty `source_node_id`,
non-empty `target_node_id`, `source_port` is actually an `OutputPort`,
`target_port` is actually an `InputPort`, then delegates to
`check_connection()`. Any violation raises `ValidationError` (reused,
no new exception type); a successful construction is therefore
always known-valid for its lifetime.

## Correctness

| Case                                                          | Expected | Result |
| ---------------------------------------------------------------- | -------- | ------ |
| Exact-type compatible pair constructs                              | success    | PASS |
| Subtype-compatible pair constructs                                     | success       | PASS |
| Incompatible pair                                                          | raises `ValidationError` | PASS |
| `InputPort` passed as `source_port`                                            | raises, names `source_port` | PASS |
| `OutputPort` passed as `target_port`                                               | raises, names `target_port` | PASS |
| Empty `source_node_id`                                                                 | raises, names `source_node_id` | PASS |
| Empty `target_node_id`                                                                     | raises, names `target_node_id` | PASS |
| Two connections sharing a source (fan-out)                                                     | both construct, remain distinct | PASS |
| Two connections sharing a target (fan-in)                                                          | both construct, remain distinct | PASS |
| Integration: Retriever→Reranker, Reranker→Generator                                                    | construct successfully | PASS |
| Integration: Retriever→Generator (deliberately incompatible)                                               | raises | PASS |

```
case_count: 11
error_count: 0
expected_outcome_accuracy: 1.0
```

## The directionality correction

The first draft of ADR-015 relied on field type annotations
(`source_port: OutputPort`, `target_port: InputPort`) alone to
guarantee directionality. This was reviewed and found insufficient
before implementation: Python does not enforce dataclass field
annotations at runtime, and `check_connection()` (ADR-014) explicitly
does not normalize non-`Port` arguments into `ValidationError` — so
`Connection(source_port=InputPort(...), ...)` would have either
constructed successfully or failed with an unrelated `AttributeError`
deep inside `check_connection()`, silently permitting a backwards
"connection." The implemented contract adds two explicit `isinstance`
checks at the `Connection` boundary specifically to close this,
without reopening ADR-014's own documented non-guarantee for
`check_connection()` itself. `test_connection_rejects_input_port_as_source`
and `test_connection_rejects_output_port_as_target` are the tests that
would have caught the original flaw.

## API quality

| Property                                                                         | Result |
| ----------------------------------------------------------------------------------- | ------ |
| Compatibility logic is not duplicated — delegates to `check_connection()` (verified by comparing error messages, not just "it also raises") | PASS |
| `check_connection()`/`is_compatible()`/`InputPort`/`OutputPort` all unchanged | PASS |
| Value equality (no synthetic identity) — consistent with `ArchitectureChild`'s precedent | PASS |
| Hashable, equal instances hash equally (frozen-dataclass default, confirmed not assumed) | PASS |
| No fan-out/fan-in constraint accidentally introduced | PASS |
| Public export parity: `Connection` present in both `ragtorch.core.__all__` and `ragtorch.__all__` | PASS |

## Functional results

20 new tests (17 unit in `tests/unit/core/test_connection.py` + 3
integration in `tests/integration/test_component_ports.py`). Combined
with the pre-existing 238, total suite is 258.

| Invariant                                                                                   | Result |
| ----------------------------------------------------------------------------------------------- | ------ |
| Valid exact-type and subtype pairs construct successfully                                          | PASS |
| Incompatible pairs raise `ValidationError`                                                             | PASS |
| Directionality enforced at runtime, not just by annotation (both directions tested)                        | PASS |
| Empty node IDs rejected independently for source and target                                                    | PASS |
| Immutable (frozen dataclass — attribute assignment raises)                                                         | PASS |
| Value equality: identical fields equal, any one differing field not equal                                             | PASS |
| Hashable; equal instances hash equally                                                                                    | PASS |
| Fan-out and fan-in both explicitly left unconstrained (two dedicated tests)                                                  | PASS |
| Delegates to `check_connection()` — proven via matching error messages, not merely "both raise"                                 | PASS |
| Retriever→Reranker→Generator chain: compatible segments construct via `Connection`                                                  | PASS |
| Retriever→Generator (deliberately incompatible) raises via `Connection`                                                                 | PASS |
| No `get_type_hints`/`eval`/`exec` in `connection.py` (source inspection)                                                                    | PASS |
| No provider import in `connection.py` (AST-based check, reusing the Step 7/10 pattern)                                                          | PASS |

## Test results

```
pytest:        258 passed (238 pre-existing, unmodified + 20 new)
ruff check:    All checks passed
ruff format:   clean
mypy:          Success: no issues found in 23 source files
coverage:      99% overall; connection.py 100%
```

Also verified directly against Python 3.10 (`py -3.10`): 258/258
passed, mypy clean.

## Performance

`benchmarks/step11_connections.py`, Windows, Python 3.12.0, local.

| Operation                                    | p50 (µs) |
| ----------------------------------------------- | -------- |
| `check_connection(valid)` [Step 10 baseline]        | 0.500    |
| `Connection(valid)`                                     | 2.400    |
| `Connection(invalid, raises)`                               | 6.700    |
| `Connection.__eq__`                                             | 0.700    |
| `hash(Connection)`                                                  | 1.100    |

`Connection(valid)` costs ~1.9µs more than `check_connection()` alone
at p50 — larger than an initial "small" prediction assumed before
measuring. The frozen-dataclass `__init__`/`__post_init__` path
(`object.__setattr__` invoked once per field, four `isinstance`/`str`
checks, one nested `check_connection()` call) is not free, even though
each individual check is cheap in isolation; this is recorded as
measured, not left as the original, incorrect prediction. Still three
orders of magnitude below any real RAG operation (retrieval, model
inference), so this is not a functional concern — it is reported
honestly rather than adjusted to match a prior expectation. No hard
threshold asserted, consistent with prior benchmarks' methodology.

## Compatibility review

| Existing API                       | Step 11 effect |
| ------------------------------------- | -------------- |
| `Component`                             | none — zero lines touched |
| `Module`/`Sequential`                       | none — zero lines touched |
| `ExecutionEngine`/`ExecutionContext`            | none — zero lines touched |
| `ArchitectureSnapshot`/`ArchitectureChild`          | none — zero lines touched |
| `validate_snapshot()`/`architecture.py`                 | none — zero lines touched |
| `InputPort`/`OutputPort`/`is_compatible()`/`check_connection()` | none — zero lines touched |
| existing exceptions                                                | unchanged — `ValidationError` reused, no new type |

All 238 pre-existing tests pass **unmodified**.

## Security review

| Question                                                    | Answer |
| ------------------------------------------------------------------ | ------ |
| Does `Connection` execute component code?                              | No |
| Does it evaluate annotations or use reflection?                            | No — verified by source inspection (no `get_type_hints`/`eval`/`exec`) |
| Does it import any provider/model dependency?                                  | No — verified by AST-based import inspection |
| Does it mutate its own fields after construction?                                  | No — frozen dataclass, proven by dedicated test |
| Does it resolve or look up `source_node_id`/`target_node_id` against anything?         | No — stored as opaque strings, not interpreted |

## Dependency review

Zero new runtime dependencies. `connection.py` imports
`ragtorch.core.errors` and `ragtorch.core.ports` (both existing
internal modules) plus the standard library `dataclasses`. Confirmed
via the existing AST-based import inspection test.

## Diff review

Scope: `src/ragtorch/core/connection.py` (new), `core/__init__.py` +
top-level `__init__.py` (export, 100%-parity convention),
`test_connection.py` (new), `test_component_ports.py` (3 new
integration tests), `test_public_api.py` (1 entry),
`benchmarks/step11_connections.py` (new), ADR-015 (new, corrected
pre-implementation, to be accepted post-CI), requirements matrix (A45+,
pending). No touch to `Component`, `Module`, `Sequential`,
`ExecutionEngine`, `architecture.py`, `inspection.py`, or `ports.py` —
confirmed by `git diff --stat main...HEAD`.

## Limitations (explicitly named, not silently absorbed)

- **No fan-out/fan-in cardinality rule.** `Connection` places no
  constraint on how many connections may share a source or target —
  proven by dedicated tests, not merely unaddressed. Whether such a
  constraint should exist, and where it would live (a future
  collection/`Block` type, not `Connection` itself), is deliberately
  undecided here.
- **No integration with `ArchitectureSnapshot`/`validate_snapshot()`.**
  `Connection` does not read or produce a snapshot; `ArchitectureChild`
  (containment) and `Connection` (data-flow) remain two independent
  concepts, per ADR-012's own non-goal that containment must never
  imply data-flow.
- **No collection/graph type.** This step proves the element in
  isolation; a future graph/`Block` layer is expected to hold a
  collection of `Connection`s, not built here.
- **`source_node_id`/`target_node_id` are unvalidated against any real
  architecture.** A `Connection` can reference node IDs that don't
  exist in any `ArchitectureSnapshot` — cross-checking against a real
  snapshot is deferred until a real consumer needs it.

## Decision

**Step 11 Definition of Done: met locally** (Python 3.10 and 3.12 both
verified). Per the project's standing discipline, ADR-015's status
change from Proposed to Accepted is deferred until real GitHub Actions
CI confirmation — not claimed from local checks alone.
