# Step 26 Evaluation — RAG Architecture Boundary Discovery

## Status

**Step 26: COMPLETE. Outcome A — no architecture change; more evidence is required
before any provider/RAG-contract boundary is designed or implemented.**

This is an audit-only step. No production code under `src/ragtorch/` was changed. No
ADR was written (none was justified — no architectural decision was made). This document
is itself the evidence record.

## Evidence vocabulary used in this document

- **Audited**: inspected directly (file read, `grep`, class signature read) — not assumed.
- **Real consumer**: production code (non-test) that actually calls/uses the concept.
- **Synthetic/test consumer**: a trivial test-double class that exists only to exercise
  unrelated framework mechanics (ports, snapshot, graph composition), not to perform the
  concept's actual function.
- **Planned**: named only in ADR/requirements/architecture-vision prose as future work,
  with no code or test artifact.
- **Zero consumer**: no code, test, or planned-with-design-detail artifact exists.

---

## Phase 1 — Repository audit (verified against GitHub `main`, not prior summaries)

1. **Current HEAD SHA**: `e0627902c07a52cf9e29334cf916c1a2a7dfd1eb`, confirmed identical
   between `git log origin/main -1` and local `git log -1` after `git fetch origin main`.
2. **Step 25 closure**: confirmed — this is the exact commit Step 25's own closure
   section names as its final commit.
3. **CI state**: `gh run list --branch main --limit 1` shows run `32072858134` on this
   exact SHA, `status: completed`, `conclusion: success`.
4. **Test count**: 528 unit/integration tests (528/528 passing per Step 25's post-merge
   evidence), plus 11 packaging tests.
5. **Package version**: `0.4.0` (`pyproject.toml:6`, matches `src/ragtorch/__init__.py`'s
   `__version__`).
6. **Public API**: `src/ragtorch/__init__.py`'s `__all__` — 60 names, all execution-kernel
   and evaluation vocabulary (`Module`, `Component`, `Sequential`, `Block`,
   `CompositionGraph`, `GraphNode`, `Connection`, `RAGModule`, `ExecutionEngine`, `Run`,
   `Trace`, `MetricsCollector`, event types, error types). **Zero RAG-domain vocabulary**
   (`Retriever`, `Embedder`, `Generator`, `VectorStore`, `Provider` do not exist as
   public names).
7. **`src/ragtorch/` structure**: exactly two subpackages, `core/` (20 files: module,
   component, sequential, block, composition, connection, ports, architecture,
   execution/execution_plan, engine, context, run, trace, metrics, events, errors,
   config, logging, inspection) and `evaluation/` (case, evaluator, metric, result). No
   `providers/`, `retrievers/`, `embeddings/`, `storage/`, or `plugins/` subpackage
   exists.
8. **`Module`/`Component` contracts**: `Module` (`core/module.py`) is a concrete base
   class with `forward`/`__call__`/registration/`snapshot`/`inspect`. `Component`
   (`core/component.py:21`) is an `@runtime_checkable Protocol[InputT, OutputT]`
   requiring only `name`, `component_type`, `__call__` — `Module` satisfies it
   structurally, no inheritance required (ADR-010).
9. **`Sequential`/`Block`/`CompositionGraph` contracts**: `Sequential(*steps: Module)`
   runs steps in order. `Block(graph: CompositionGraph, *, input_node, output_node)`
   wraps a graph as a reusable `Module` (ADR-020). `CompositionGraph` is an immutable
   frozen dataclass (`nodes: tuple[GraphNode, ...]`, `connections: tuple[Connection,
   ...]`) requiring both arguments at construction (no incremental builder reachable
   from the constructor), validated for uniqueness, referential integrity, fan-in ≤1,
   and acyclicity (ADR-016). `RAGModule` (`core/module.py:287`) is a **marker base
   class** with one additive classmethod, `from_graph()`, that internally wraps a
   `Block` via a private adapter (ADR-021) — it carries no RAG-specific semantics itself.
10. **Evaluation abstractions**: `Evaluator(metrics, ...).evaluate(system, cases)` where
    `system` is `Callable[[Any], Any]` — explicitly not `Module`-coupled
    (`evaluator.py:16-18`: "the evaluator does not depend on Module, so it can score
    non-ragtorch systems too"). `Metric` is a Protocol; `ExactMatch`/`Latency` are the
    only concrete implementations. `evaluation/metric.py:3-4` explicitly notes an
    "LLM-as-judge" metric is a **future, undesigned** `Metric` implementation, not
    special-cased.
11. **Serialization/inspection/observability**: `ArchitectureSnapshot`/`snapshot()`/
    `validate_snapshot()` (ADR-012/013) give an immutable tree description; no
    graph-level (`CompositionGraph`) serialization exists yet — deferred, per A65's own
    text, "Serialization remains future work" (`__init__.py:74`). `Trace`/`Span`/
    `MetricsCollector`/structured `logging` are fully general, provider-agnostic.
12. **ADRs concerning providers/adapters**: **ADR-005 (Provider Independence)** is the
    governing decision — core must never import/require a specific model provider,
    embedding service, vector DB, or orchestration framework; provider code is an
    adapter behind a stable interface, shipped as an optional extra. No ADR has yet
    defined *what that interface actually is* — ADR-005 states the constraint, not the
    contract shape.
13. **Requirements-matrix rows related to RAG/providers/embeddings/storage/retrieval/
    LLMs/multimodal/Graph RAG/plugin boundaries**: R1 (vendor independence, "Provider
    contracts not yet implemented"), R2 (model independence, "No model contract yet"),
    R3 (storage independence, "No storage contract yet"), R6 (replaceability, "Future
    Component/Port contracts needed"), R11 (optional dependencies, "Provider extras not
    yet implemented"), A3 (RAGModule semantics "too weak"), A6/A7 (provider
    routing/fallback, absent), A8 (evaluation-gating runtime behavior, absent), A11
    (plugin/dependency boundary — explicitly **Deferred** per Step 24/A76: "No plugin
    system exists yet to separate"). **No row is named for embedding, LLM, or
    multimodal specifically** — those terms appear only inside R1/R2/R3/A11's prose and
    in narrative "explicit non-goals" sections, never as their own tracked requirement.
14. **Deferred architecture gaps**: A76 (Step 24) already ran a 12-candidate gap audit
    that explicitly considered every provider/routing/plugin candidate here (R1/R2/R3,
    A3, A6/A7, A8, A11) and found **zero real, synthetic, or planned-in-code consumer**
    for any of them via direct source search — the same conclusion this step
    independently re-confirms with a more exhaustive, RAG-specific keyword sweep.
15. **Documentation describing the intended future RAG layer**: `docs/architecture/
    v0.1-architecture.md` is the primary vision document. §1: the framework should let a
    developer build "Basic RAG, Hybrid RAG, Graph RAG, Multimodal RAG, Agentic RAG"
    without modifying core. §3 names illustrative future Components: "Retriever,
    Generator, Embedder, Reranker, Chunker, Router, Parser, Fusion, Validator." §8:
    "Providers are adapters, never the foundation of core" — diagram shows a stable
    contract with adapters (Ollama/vLLM/Hugging Face/cloud) behind it. §9: provider
    routing/fallback is "intentionally future work; no provider router is implemented in
    this step." §15 explicit non-goals (dated to Step 5, still true today): "Do not
    implement yet: LLM integrations; embedding providers; vector databases; graph
    databases; automatic model fallback; quality-gated routing..." This document is
    aspirational/directional, not a frozen contract — it names *what* should eventually
    be pluggable, not *how*.

## Phase 2 — Current RAG capability audit (keyword sweep)

Full results (exhaustive, case-insensitive, `src/`+`tests/`+`docs/`+`benchmarks/`+
`evaluation/`) gathered via a dedicated research pass. Summary table (see the full
per-match breakdown in the background audit; condensed here for the ledger):

| Keyword | Production (A) | Contract (B) | Test-only (C) | Docs-only (D) | Benchmark (E) | Dead (F) | Unrelated (G) |
|---|---|---|---|---|---|---|---|
| embedding | 0 | 0 | 0 | 12 | 0 | 0 | 0 |
| vector | 0 | 0 | 1 (span label) | 3 | 0 | 0 | 0 |
| retriever | 0 | 0 | ~7 (test doubles) | 2 | 0 | 0 | 0 |
| retrieval | 0 | 0 | 0 | many | 0 | 0 | 0 |
| document | 0 | 0 | 0 | many | 0 | 0 | most of 267 |
| chunk | 0 | 0 | 2 (span labels) | several | 0 | 0 | 0 |
| splitter / loader / image | 0 | 0 | 0 | 0 | 0 | 0 | 0 (zero matches at all) |
| generator | 0 | 0 | ~7 (test doubles) | 1 | 0 | 0 | most of 111 |
| llm | 0 | 0 | 0 | 4 | 0 | 0 | 0 |
| prompt | 0 | 0 | 0 | 2 | 0 | 0 | 0 |
| multimodal | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| vision | 0 | 0 | 0 | 1 (hypothetical example) | 0 | 0 | 16 ("revision"/"provision") |
| graph rag / knowledge graph | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| reranker | 0 | 0 | ~4 (test doubles) | 1 | 0 | 0 | 0 |
| citation | 0 | 0 | 0 | 0 | 0 | 0 | 2 (audit-process citations) |
| provider | 0 | 0 | few (absence-asserting) | most of 166 | 0 | 0 | 0 |
| adapter | 1 (`_GraphBackedRAGModule`, framework-internal glue) | 0 | 0 | most of 36 | 0 | 0 | 0 |
| plugin | 0 | 0 | 0 | 9 | 0 | 0 | 0 |

**Conclusion**: zero production RAG implementations exist anywhere. The one "adapter" hit
classified **A** (`module.py:324`) is `Block`→`RAGModule` framework-internal glue
(ADR-021), not a provider/vendor adapter — it adapts one part of this framework's own
kernel to another, unrelated to the provider-boundary question this step investigates.

## Phase 3 — Real consumer audit

| # | Concept | Classification | Evidence |
|---|---|---|---|
| 1 | Document ingestion | Zero | No loader/ingestion code anywhere; "document" in `src/` is docstring prose only (`ports.py:30-31`, `logging.py:12,65`) |
| 2 | Chunking | Zero | `splitter`: 0 matches. `chunk`: only synthetic `trace.start_span("chunker")` test labels |
| 3 | Embedding generation | Zero | All 12 matches are docstrings/ADRs stating embeddings are explicitly not yet implemented |
| 4 | Vector storage | Zero | Only docstring mentions + one synthetic test span label (`"vector_search"`) |
| 5 | Retrieval | Test / Planned | `Retriever`/`FakeRetriever` test doubles across 6 test files, used only to exercise unrelated mechanics (ports, snapshot, graph); named as future work in requirements.md R6 and v0.1-architecture.md §3 |
| 6 | Reranking | Test / Planned | Same pattern as retrieval, same test files |
| 7 | Prompt construction | Zero | No `Prompt` type anywhere; only redaction-policy prose |
| 8 | LLM generation | Test / Planned | `Generator`/`FakeGenerator` test doubles, same files; "LLM-as-judge" `Metric` explicitly named as undesigned future work |
| 9 | Citation/source tracking | Zero | Two matches, both referring to unrelated audit-process citations |
| 10 | Multimodal input | Planned (doc-only) | 3 matches, all in `v0.1-architecture.md`/evaluation docs; zero code, zero tests |
| 11 | Image retrieval | Zero | `image`: 0 matches anywhere. `vision`: false positives except one hypothetical naming-collision example in ADR-011 |
| 12 | Graph retrieval | Zero (planned mention only) | 3 matches, all documentation-level aspiration. `CompositionGraph` is a real, implemented generic execution-DAG for wiring `Component`s — it carries **no** retrieval/embedding/knowledge-graph semantics |

**Every one of the 12 RAG-specific concepts has zero real production consumer.** Five
have test-only synthetic stand-ins that exist purely to exercise unrelated framework
mechanics (never to simulate the concept's actual behavior). This independently
reproduces and strengthens A76's (Step 24) conclusion using RAG-specific vocabulary
rather than architecture-gap vocabulary.

---

## Phase 4 — Provider boundary design-space comparison

Six candidate boundaries compared against 20 criteria. Since **Outcome A** was reached
(see Phase 12), this comparison is recorded as evidence gathered, not as a chosen design
— no boundary is being committed to yet.

| Criterion | A. Interfaces in core | B. Separate package | C. Adapter/plugin boundary | D. Protocol/structural | E. Generic Module-based | F. Hybrid (Protocol + Module) |
|---|---|---|---|---|---|---|
| 1. Provider independence | Weak — core importing provider types couples core to their shape even if unused | Strong — provider code physically cannot leak into core | Strong, but requires a discovery/registration mechanism that doesn't exist yet (A11 still deferred) | Strong — a Protocol has zero runtime import cost, structural typing needs no shared base | Moderate — reuses `Component`, but forces every provider concept into `forward(input) -> output`, which may not fit (e.g. batch embedding) | Strong — Protocol defines the contract, Module is only one possible implementation strategy |
| 2. Python 3.10 compat | Fine | Fine | Fine | Fine (`Protocol` since 3.8) | Fine | Fine |
| 3. Testability without network | Depends on discipline | Easy — fakes live wherever tests need them | Easy | Easy — any object satisfying the shape works, no inheritance | Easy — `Module` subclasses are already the established fake pattern in this repo's own tests | Easy |
| 4. Mockability | Same as any Python code | Same | Same | Best — structural typing means a bare function/dataclass can satisfy it | Good — same pattern already used for `Retriever`/`Generator` test doubles today | Best of both |
| 5. Future async support | Would require a second interface or `Awaitable`-returning contract either way | Same | Same | Cleanest — a `Protocol` can define `async def` methods without touching `Module`'s existing sync `__call__` | `Module.__call__` is sync-only today (A16-enforced hot path); forcing async through it risks a breaking change to the core hot path | Cleanest — async concern isolated to the Protocol, `Module` wrapper is optional |
| 6. Serialization | Would need to be designed either way — nothing existing (`ArchitectureSnapshot`) covers graph-level or provider-level serialization yet | Same | Same | Same | Same | Same |
| 7. Observability | `ExecutionEngine`/`Trace`/`EventBus` are already provider-agnostic; any boundary composes with them for free as long as the provider is wrapped as (or delegates to) a `Module`/`Component` at some point | Same, as long as boundary is used inside a `Module` eventually | Same | A bare Protocol implementation gets zero observability for free — must be wrapped | Full observability for free — this is `Module`'s existing guarantee | Full observability for free when wrapped, flexible when not |
| 8. Failure isolation | No existing precedent to reuse | No existing precedent | Requires new isolation machinery | No isolation built in — caller's responsibility | Reuses `ListenerDeliveryError`-style isolation only if wired through `EventBus`, not automatic | Same as E |
| 9. Streaming | Nothing existing supports this — would be new contract surface for any option | Same | Same | Cleanest to add later (Protocol can gain a new method) | `Module.__call__`'s single-input/single-output shape doesn't naturally express a stream today | Cleanest |
| 10. Batch operations | Same "nothing exists yet" for all options | Same | Same | Easy to express as a distinct Protocol method later | Awkward to retrofit onto `forward(input) -> output` | Easy |
| 11. Multimodal support | Depends entirely on what `Document`/`Content` type is chosen (Phase 6) — orthogonal to boundary choice | Orthogonal | Orthogonal | Orthogonal | Orthogonal | Orthogonal |
| 12. Graph RAG support | Orthogonal — depends on whether Graph RAG is a Retriever variant (Phase 7) | Orthogonal | Orthogonal | Orthogonal | Orthogonal | Orthogonal |
| 13. Version compatibility | Provider SDK version bumps could ripple into core if types are imported there | Isolated entirely to the extra package | Isolated | Isolated (pure structural typing, no shared version-locked base) | Isolated as long as `Module` itself stays stable | Isolated |
| 14. Optional dependencies | Hard to keep truly optional if core imports provider types for typing | Clean — separate package, separate extras | Clean | Cleanest — Protocols need no imports from the provider package at the point of definition | Clean, same as A11's existing "core has no provider dependency" invariant | Clean |
| 15. Dependency isolation | Risk of accidental coupling | Strong | Strong | Strong | Strong (already proven — `Component`/`Module` have zero provider deps today) | Strong |
| 16. Public API stability | Every provider type added to core risks becoming an accidental part of the public contract | Provider-package APIs can evolve independently of `ragtorch` core's own stability guarantees | Depends on adapter interface design | A frozen Protocol shape is a strong, narrow stability surface | `Module`'s `__call__`/`forward` contract is already the project's most stable, most-tested surface (ADR-001, A16) | Best — narrow Protocol + already-proven Module stability |
| 17. Ease of replacing providers | Same regardless of boundary — determined by contract narrowness, not location | Same | Same | Same | Same | Same |
| 18. Performance | No measurable difference — this is a typing/organization question, not a runtime one | Same | Same | Same | Same (though enforcing every provider call through `Module.__call__`'s existing hot-path is already benchmarked cheap, A16/A76) | Same |
</br>
| 19. Type safety | Weaker if using loosely-typed adapter registries | Same as A | Depends on registry design | Strongest — `Protocol[InputT, OutputT]` already exists and is `mypy --strict`-checked today (`Component`) | Strong, reuses existing generic `Component[InputT, OutputT]` | Strongest |
| 20. Developer ergonomics | Simple for small projects, but risks "everything lives in core" sprawl this project has consistently avoided (see A76, A61, A11 all rejecting speculative core growth) | Extra indirection (a second package to install/import) for what might be a small contract | Requires a plugin/registry system this project has explicitly deferred (A11) | Very light — a Protocol costs nothing until someone implements it, matches this project's `Component` precedent exactly | Familiar — reuses the same `Module` pattern every existing test double already follows | Most flexible, but also the most surface area to get wrong prematurely |

**Observation, not decision**: options D (pure Protocol) and F (hybrid) score best on
the criteria this project has consistently valued in its own ADR history (ADR-010's
`Component` Protocol precedent, ADR-005's provider-independence rule, A11's deferred
plugin boundary, A76's rejection of speculative infrastructure). But — critically — this
comparison does not, by itself, justify implementing anything: Phase 12's decision below
explains why.

## Phase 5 — Minimum RAG contract inventory (design-only, NOT implemented)

For each candidate abstraction, the question asked is whether *today's evidence*
justifies designing (not implementing) it now.

| Abstraction | Necessary now? | Notes |
|---|---|---|
| `Document` | No | No ingestion consumer exists (Phase 3 #1). Shape (text-only vs. multimodal) cannot be responsibly decided without at least one real retrieval consumer to validate against — deciding now risks exactly the kind of speculative design this project's own history (A61, A76) has repeatedly rejected. |
| `Chunk` | No | Same reasoning; additionally depends on `Document`'s shape. |
| `Embedding` / `EmbeddingModel` | No | Zero consumer; provider-specific shapes (dimensionality, distance metric assumptions) vary enough across real providers that a contract designed with zero real integration would be guessing. |
| `VectorStore` | No | Same; R3 already names this as a frozen future requirement, not something to design speculatively. |
| `Retriever` | No | Test doubles already exist and work fine as `Module`/`Component` satisfiers for exercising unrelated mechanics — no evidence a *dedicated* `Retriever` contract (beyond what `Component` already offers structurally) is needed yet. |
| `RetrievedDocument` / `RetrievalResult` | No | Depends on `Document`. |
| `Reranker` | No | Same as `Retriever`. |
| `PromptTemplate` | No | Zero consumer, zero design precedent in this codebase for templating. |
| `Generator` / `LLM` | No | Same as `Retriever`; `evaluation/metric.py` already explicitly defers "LLM-as-judge" for the identical reason (no real consumer to validate the shape against). |
| `Citation` / `Source` | No | Zero footprint at all. |
| `RAGPipeline` | No | `Sequential`/`Block`/`RAGModule.from_graph()` already compose arbitrary `Module`s into pipelines — no evidence a RAG-specific pipeline type adds anything beyond what composition already provides. |

**Every abstraction in this list fails the "necessary now?" gate.** None are designed in
this step. This matches the project's own hard rule (A76, A61, A11): an abstraction
needs a real, synthetic-with-real-design-pressure, or concretely planned-in-code
consumer — not just a name in a vision document — before it is designed, let alone
implemented.

## Phase 6 — Multimodal/vision architecture audit (evidence only)

Zero code, zero tests, zero real or synthetic consumer for any multimodal concept
(Phase 3 #10, #11). `v0.1-architecture.md` §3 names `MultimodalBlock` only as an
illustrative future example, with no design detail. There is currently no `Document`
type of any kind to extend with typed content parts, so comparing "universal Content
abstraction" vs. "typed content parts" vs. "modality-specific documents" would be
comparing hypothetical designs with no grounding evidence — explicitly out of scope for
an evidence-first step per this project's standing discipline. **No comparison is
recorded as a decision; this is deferred pending a real text-only RAG consumer first.**

## Phase 7 — Graph RAG audit

`CompositionGraph`/`GraphNode` (ADR-016) are real, implemented, and audited directly:
they form a generic, immutable, validated execution/composition DAG for wiring
`Component`s together (fan-in ≤1, acyclic, referential integrity). They carry **zero**
retrieval, embedding, or knowledge-graph-specific semantics — confirmed by reading
`composition.py`'s full class definition (Phase 1 item 9) and finding no
retrieval/entity/relationship vocabulary anywhere in it.

**Explicit finding**: `CompositionGraph` must not be confused with a future
application-level knowledge graph. It answers "how are these Components wired for
*execution*," not "what entities and relationships exist in the retrieved corpus." A
Graph RAG implementation would need its own, separate knowledge-graph/traversal
abstraction — `CompositionGraph` is not a candidate for that role, and this step makes
no attempt to design one, matching Phase 5's "not necessary now" conclusion for every
RAG-specific type. Since there is no `Retriever` contract yet either (Phase 5), the
question of whether Graph RAG should be "a Retriever implementation" vs. "a separate
pipeline" is unanswerable with current evidence — it is not decided here.

## Phase 8 — Optional dependency design (evidence only)

Audited `pyproject.toml` (Step 25 work): `dependencies = []` (zero runtime deps today),
`dev` extras are the only optional-dependency group that exists. R11 already names the
target shape (`ragtorch[ollama]`, `ragtorch[qdrant]`, etc.) as a frozen future
requirement. Step 25's clean-install CI work (A77) already proves the packaging
*mechanism* (wheel/sdist build, clean-venv install, CI verification across 3.10/3.11/
3.12) is sound and would compose correctly with future extras — installing `ragtorch`
bare would continue to pull zero heavy dependencies regardless of what extras are later
added, since `hatchling`/`pyproject.toml` extras are additive and opt-in by construction.
**No extras are added in this step** — there is nothing to gate behind an extra yet,
since no provider code exists.

## Phase 9 — Security review (risks only, no mechanisms implemented)

| Risk | Belongs to |
|---|---|
| Prompt injection | Application layer (depends entirely on how a future `PromptTemplate`/`Generator` boundary is designed — no such boundary exists yet to assign this to) |
| Retrieved-document injection | Application layer / future `Retriever` contract design |
| Malicious metadata | Future `Document`/`Chunk` contract design |
| Untrusted documents | Application layer (ingestion, which doesn't exist yet) |
| Remote provider responses | Adapters (once they exist) — core must never trust or deserialize provider responses without validation, consistent with ADR-005's isolation intent |
| Secrets/API keys | Adapters — `core/logging.py`'s existing redaction policy (`is_sensitive_key`, `redact()`) already exists and is provider-agnostic; any future provider adapter must route logging through it rather than inventing its own |
| SSRF through loaders | Application layer / future ingestion design |
| Unsafe deserialization | Core, if/when graph or snapshot serialization (already named as "future work," Phase 1 item 11) is designed — must not use `pickle` or similarly unsafe formats for anything crossing a trust boundary |
| Oversized documents | Application layer / future ingestion design |
| Embedding denial-of-service | Adapters (rate limiting, batching policy belongs with the provider adapter, not core) |
| Vector-store poisoning | Adapters / application layer |
| Graph poisoning | Adapters / application layer (once a knowledge-graph abstraction exists — see Phase 7) |
| Multimodal malicious content | Application layer / future ingestion design |

No mechanism is implemented for any of these — this table exists so a future step
designing these contracts has this risk inventory available rather than re-deriving it.

## Phase 10 — Performance model (evidence only, no optimization)

No production RAG code exists, so there is nothing to benchmark (see Phase 14). Cost
centers that will eventually matter, by informed expectation only (not measured, since
nothing exists): embedding generation and LLM generation are almost certainly the
dominant costs (network-bound, provider-side); vector retrieval and reranking are
typically the next tier; ingestion/chunking are usually cheap unless documents are very
large. Batching/caching/streaming/async are all reasonable *future* fits for
embedding/generation specifically — but per the Phase 12 decision, none of this is
designed or implemented now, only noted as expected shape for whenever real evidence
arrives.

## Phase 11 — Adversarial review

1. **Can a user replace one LLM with another?** Not yet answerable — no LLM contract
   exists to test replaceability against.
2. **Can they replace one embedding model with another?** Same — no contract exists.
3. **Can they replace FAISS with Qdrant?** Same — no VectorStore contract exists.
4. **Can retrieval work without a specific provider?** Trivially yes today, because
   retrieval doesn't exist at all yet — this isn't evidence of good design, just absence.
5. **Can a fake embedding provider be used in unit tests?** Not applicable — nothing to
   fake.
6. **Can an LLM be mocked?** Not applicable.
7. **Can a retriever be mocked?** Yes, today, via the existing `Module`/`Component`
   pattern already proven in 6+ test files (Phase 3 #5) — this is real, working evidence
   that whatever future `Retriever` contract emerges can likely reuse this exact,
   already-battle-tested mocking style.
8. **Can a multimodal document exist without forcing text-only components to understand
   images?** Unanswerable without a `Document` design — explicitly deferred (Phase 6).
9. **Can Graph RAG coexist with normal RAG?** Unanswerable without a `Retriever`
   contract to know whether Graph RAG would be a variant of it or a separate concept
   (Phase 7).
10. **Can providers be versioned independently?** Yes, structurally guaranteed by
    ADR-005 and Step 25's optional-dependency-extras plan (Phase 8) — provider SDKs
    would live in separate extras, never core's own dependency list.
11. **Can optional dependencies remain optional?** Yes — proven by Step 25's clean-install
    CI evidence (A77): the core wheel has zero runtime dependencies today, and
    `hatchling` extras are additive by construction.
12. **Can the public API survive provider changes?** Only if the eventual contract is
    narrow and structural (Protocol-based) rather than importing provider SDK types
    directly — this favors design options D/F from Phase 4, but is not decided here.
13. **Can the system eventually support async?** Only if the future contract is designed
    separately from `Module.__call__`'s existing sync hot path (A16-protected,
    benchmarked) — favors Protocol-based options (D/F) over forcing everything through
    `Module` (E), per Phase 4 row 5.
14. **Can it eventually support streaming?** Same reasoning as #13.
15. **Can all of this remain observable through the existing execution kernel?** Yes, as
    long as any future provider adapter is eventually wrapped in (or delegates to) a
    `Module`/`Component` at some point before or after the actual provider call — this
    is exactly the same pattern `Block`/`RAGModule.from_graph()` already use for
    graph-backed composition (ADR-020/021), so there is a proven, working precedent to
    follow later.

**Adversarial conclusion**: none of these questions are actually testable today because
no contract exists — the honest answer to most of them is "unknown, not yet
falsifiable," which is itself evidence that designing a contract now would be guessing
rather than engineering against real constraints.

## Phase 12 — Decision

**Outcome A: No architecture change yet; more evidence is required.**

Justification, tied directly to the instruction's own hard rule (every abstraction must
answer who uses it, what problem it solves, what evidence proves the problem exists):

- Phase 2/3 exhaustively confirm **zero real production consumer** for every one of the
  12 RAG-specific concepts audited (document, chunk, embedding, vector store, retrieval,
  reranking, prompt, LLM generation, citation, multimodal, image retrieval, graph
  retrieval).
- The handful of test-only `Retriever`/`Generator`/`Reranker` doubles that exist
  (Phase 3 #5, #6, #8) are not evidence of a needed contract — they are trivial `Module`
  subclasses used to exercise *unrelated* mechanics (ports, snapshot rendering, graph
  composition, event scoping). They already work fine as-is; nothing about them is
  straining against a missing abstraction.
- This independently reproduces and reinforces Step 24's own A76 finding (a 12-candidate
  architecture-gap audit that reached the identical conclusion using different
  vocabulary) — this is now the *second* independent audit to find no real consumer for
  the provider/RAG boundary, strengthening rather than merely repeating that evidence.
- Phase 4's design-space comparison suggests Protocol-based options (D/F) would likely
  score best *if and when* a decision is made — but Phase 11's adversarial review shows
  most of the actual replaceability/async/streaming questions are unfalsifiable without
  a real consumer to test them against. Choosing a boundary now would be committing to
  answers for questions that cannot yet be verified.
- This project's own established discipline (A11, A61, A76) has consistently rejected
  building infrastructure ahead of a real consumer, even when the design looked
  "obviously right" — Outcome A is the same discipline applied here, not a novel or
  more cautious standard invented for this step.

**Outcome B (define the boundary + ADR) and Outcome C (implement contracts) are both
explicitly rejected** — not because the design work in Phases 4-11 is worthless (it is
preserved here precisely so a future step doesn't have to re-derive it), but because
committing an ADR or code to a specific contract shape without a real consumer to
validate it against would be exactly the "implementing because it sounds
architecturally beautiful" anti-pattern this step's own hard rule forbids.

**Outcome D (split into a separate package) is rejected** — there is nothing to split
yet; no RAG-layer code exists in this repository to move.

## Phase 13 — Test strategy

No production code changed, so no new production feature tests are added, per the
instruction's own rule ("No production feature tests unless production code changes").

## Phase 14 — Benchmark

No production code changed. No benchmark is added. Justification: there is no new
runtime behavior to measure — fabricating a benchmark against nonexistent RAG code would
produce a meaningless number, which this project's own established discipline (Step 24's
A76: "No benchmark file: this is a static AST check with no runtime execution path")
explicitly rejects doing.

## Phase 15 — Documentation

- No ADR is created — no new architectural decision was made (Outcome A). ADR-005
  remains the governing decision; nothing here supersedes or extends it.
- Requirements matrix: appending row **A78** (next free ID, confirmed via direct `grep`
  against the live file, not assumed) recording this step's evidence, per the
  append-only convention — A1-A77 remain historically frozen.
- This document (`evaluation/step26-evaluation.md`) is the full evidence record.

## Phase 7 (compatibility/security/dependency reviews, git diff review)

- **Compatibility review**: zero changes to `src/ragtorch/**` — confirmed via
  `git diff --stat` (see Phase 16). Public API, all existing contracts, and all 528
  existing tests are unaffected by this step.
- **Security review**: see Phase 9 — risk inventory only, no code changes to review for
  vulnerabilities since none was written.
- **Dependency review**: no new dependency, runtime or dev, was added in this step.
- **Git diff review**: this step's diff is confined to
  `evaluation/step26-evaluation.md` (new) and
  `docs/architecture/requirements-matrix-v0.1.md` (one new appended row, A78). No other
  file is touched.

## Phase 16 — Git / CI evidence

(Filled in after real GitHub-facing work completes — see below.)

## Unresolved risks

- The provider/RAG contract boundary remains fully undesigned. This is intentional
  (Outcome A), not an oversight — but it means every downstream RAG feature request
  will need its own real-consumer evidence before any contract can be responsibly
  designed.
- `docs/architecture/v0.1-architecture.md` remains aspirational/directional prose, not a
  frozen contract — future steps should continue treating it as a source of candidate
  future work, not as an implied specification.
- A78 (this step) explicitly does not resolve R1/R2/R3/R6/R11/A3/A6/A7/A8/A11 — all
  remain open and Deferred, re-confirmed rather than resolved, exactly as A76 was
  before it.

## Exact conclusion

No architecture change was made. This step's evidence — a second independent,
RAG-vocabulary-specific audit finding zero real consumers for every candidate RAG
abstraction — reinforces rather than merely repeats Step 24's (A76) conclusion. The
provider-boundary design-space comparison (Phase 4) and minimum-contract inventory
(Phase 5) are preserved in this document precisely so that whenever a real consumer
does appear, that future step does not have to re-derive this evidence from scratch —
but no commitment is made today to any specific boundary, contract, or package
structure.
