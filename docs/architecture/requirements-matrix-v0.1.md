# RAG-MODULE v0.1 Requirements Matrix

This matrix converts the frozen requirements into verifiable engineering obligations and adds the architectural requirements introduced by the v0.1 direction.

| ID | Requirement | Current evidence | Gap | Planned verification |
|---|---|---|---|---|
| R1 | Vendor independence | ADR-005; no provider runtime dependency | Provider contracts not yet implemented | import/core isolation tests |
| R2 | Model independence | Provider-independence ADR | No model contract yet | provider contract tests |
| R3 | Storage independence | Requirement frozen | No storage contract yet | adapter contract tests |
| R4 | Observability independence | local Trace/Metrics/logging | Events lack execution identity | event/context tests |
| R5 | Evaluation first | evaluation package + step reports | Architecture evaluation contract still evolving | per-feature scorecard |
| R6 | Replaceability | Module contract | Future Component/Port contracts needed | contract compatibility tests |
| R7 | Composability | Module registration + Sequential | No general Block/Graph model | composition contract tests |
| R8 | Inspectability | Module.inspect()/repr() | No structured architecture snapshot | snapshot tests |
| R9 | Reproducibility | ExecutionContext + evaluation metadata | Run artifact schema incomplete | deterministic metadata tests |
| R10 | Security by default | redaction + sensitive-key detection | Need architecture snapshot secret policy | secret exclusion tests |
| R11 | Optional dependencies | pyproject extras direction | Provider extras not yet implemented | dependency/import CI |
| R12 | Backward compatibility | public API contract test | Migration strategy for Component missing | API contract suite |
| R13 | Performance budgets | Step 1-4 benchmarks | Step 5 event-context overhead must be measured | benchmark + regression threshold |
| R14 | Local-first | current core is offline | Future providers must preserve offline core | offline CI path |
| R15 | Cloud-optional | no cloud requirement | Future enterprise layer undefined | packaging/import boundary tests |
| A1 | Component is the stable conceptual unit | Module currently acts as unit | Need explicit Component contract | ADR + contract tests |
| A2 | Blocks compose Components | Sequential exists | Block abstraction not yet formalized | nested composition tests |
| A3 | Architectures are user-defined | RAGModule marker exists | RAGModule semantics too weak | architecture contract |
| A4 | Runtime is separate from business logic | ExecutionEngine exists | Runtime ownership boundaries need formalization | engine/component integration tests |
| A5 | Explicit execution identity | ExecutionContext + Step 4 | EventBus events currently lack context | event identity tests |
| A6 | Provider routing is policy-driven | only provider ADR | Router/fallback absent | future policy tests |
| A7 | Local-only fallback is enforceable | local-first requirement | no routing layer | future security/policy tests |
| A8 | Evaluation can gate runtime behavior | evaluation is post-execution today | quality-gate policy absent | future routing evaluation |
| A9 | Architecture inspection has one source of truth | string inspect exists | no structured snapshot | snapshot contract tests |
| A10 | No global mutable execution state | explicit context | process-wide EventBus remains | isolate event delivery from execution state |
| A11 | Core remains dependency-light | core has no provider dependency | future plugins not yet separated | import graph/packaging tests |
| A12 | Every major feature has tests + benchmark + evaluation | established through Step 4 | must continue | milestone checklist |

## Priority for Step 5

1. Close A5/A10: execution-scoped observability events.
2. Freeze the Component contract before implementing it.
3. Add contract tests for the future abstraction without changing existing user behavior.
4. Introduce the structured architecture snapshot design.
5. Record the baseline and update CI if required.

The Component migration is intentionally **not** a rename of `Module` in this step. We first prove the contract and compatibility boundary.
