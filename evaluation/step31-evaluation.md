# Step 31 Evaluation — RAG Framework Comparative Architecture Audit

## Status

**Step 31: COMPLETE. Outcome A — no architectural change to `src/ragtorch/`
is justified by this audit.** One concrete, evidence-backed gap was
found (`CompositionGraph`'s fan-in ≤ 1 restriction blocks a real future
consumer shape — hybrid dense+sparse retrieval fusion), but the
evidence does not yet justify changing it: no real consumer requires it
today (`examples/rag_consumer/` uses `Sequential`, not
`CompositionGraph`, and doesn't need fan-in), and ADR-016 already
recorded this as a known, deliberately deferred limitation, not an
oversight. This is recorded as a **named, evidence-strengthened open
risk**, not fixed.

**Note on numbering**: the task instruction that requested this work
called it "Step 30." However, `evaluation/step30-evaluation.md` already
exists on `main` as the real, merged evaluation ledger for the prior
"real external RAG consumer application" task. Per this project's
append-only, never-overwrite convention, this document uses the next
genuinely free number, **Step 31**, rather than colliding with existing
history. It is not a continuation of the Step 1-29 architectural
sequence; per the task's explicit instruction, no new architectural
step is auto-started after this one.

---

## 31A — Repository audit

- `git rev-parse HEAD` / `origin/main`: both `4e4ed395664456ffa1ca2bad4674e1fd0e5cc66e`,
  confirmed matching the task's stated SHA after `git fetch origin main`.
- `git status`: clean before starting (one unrelated untracked scratch
  file, `my_rag.py`, predating this task).
- Baseline `pytest -q`: **549 passed, 13 deselected**, run before any
  change.
- Current kernel primitives inventoried directly from source (not from
  memory): `Module`/`Component` (`core/module.py`, `core/component.py`),
  `Sequential` (`core/sequential.py`, a strict `value = step(value)`
  chain — re-confirmed via `inspect.getsource` against the real
  installed `ragmodel==0.5.0` package), `Block`/`CompositionGraph`
  (`core/block.py`, `core/composition.py` — immutable, validated DAG,
  **fan-in ≤ 1 per input port, no aggregation primitive**, confirmed
  both by reading `composition.py`'s validation code and by a live
  test against the installed package — see 31C/31F below), `InputPort`/
  `OutputPort`/`Connection` (`core/ports.py`, `core/connection.py`),
  `ExecutionEngine`/`ExecutionContext`/`Run`/`Trace`/`Span`/
  `MetricsCollector` (`core/engine.py`, `core/context.py`, `core/run.py`,
  `core/trace.py`, `core/metrics.py` — `Trace`/`Span` confirmed via
  direct source read to be **vendor-neutral by explicit design, zero
  dependency on OpenTelemetry or any observability vendor**, per
  `trace.py`'s own docstring and ADR-003), `EventBus`/`Event`
  (`core/events.py`), `evaluation` package (`Evaluator`/`Metric`/
  `EvaluationCase`, explicitly not coupled to `Module` — "the evaluator
  does not depend on Module, so it can score non-ragtorch systems too").
- README's stated non-goals re-confirmed unchanged and still accurate:
  no embeddings, vector databases, LLM providers, document loaders,
  chunking framework, rerankers, multimodal/vision providers, GraphRAG.

## 31B — Existing consumer analysis (`examples/rag_consumer/`)

Read every module in `examples/rag_consumer/src/` directly.

| Piece | Application-level? | Depends on ragtorch? | Would benefit from a stable ragtorch contract? |
|---|---|---|---|
| `scraper.py` (web scraping) | Yes, entirely | No | No — nothing about scraping is execution-kernel-shaped |
| `dataset.py` (HTML cleaning, `Document`) | Yes | No | Maybe eventually (see 31E), but zero evidence today |
| `chunking.py` | Yes | No | No — pure data transformation, no execution semantics needed |
| `embeddings.py` (`Embedder` Protocol) | Yes | No | No — a plain Protocol was sufficient; no `Module`/`Component` coupling needed |
| `vector_store.py` (`VectorStore` Protocol) | Yes | No | No — same reasoning |
| `retriever.py` (`Retriever(Module)`) | Partially — wraps app logic in a `Module` | **Yes** | Already uses the exact contract that exists (`Module`) |
| `reranker.py` (`Reranker(Module)`) | Partially | **Yes** | Same |
| `prompt_builder.py` | Yes, deliberately a plain function | No | Explicitly chosen NOT to be a `Module` — no meaningful execution lifecycle to trace separately (documented design decision in the demo's own README) |
| `generator.py` (`Generator(Module)`) | Partially | **Yes** | Same as Retriever/Reranker |
| `pipeline.py` (`Sequential` composition, `PipelineState`) | Glue | **Yes**, directly | Already the primary integration point |
| `evaluation.py` (hit@k, MRR, citation presence) | Yes, entirely | No | **This is the one candidate worth naming precisely — see 31E** |

**Which abstractions would create unnecessary coupling if moved into
ragtorch:** `Embedder`, `VectorStore`, `Document`/`Chunk` — all are
domain-specific data shapes with no execution semantics; forcing them
into `ragtorch.core` would violate ADR-005 (provider independence) for
zero benefit, since `Module`/`Component` already let the demo wrap
whatever it needs.

**Which abstractions could become provider-independent interfaces
without coupling to a vendor:** none identified with real supporting
evidence. `Embedder`/`VectorStore` are *already* provider-independent
Protocols — but they are demo-specific data shapes (`embed_documents`,
`add`/`search`), not execution primitives, so "provider-independent"
does not automatically mean "belongs in ragtorch."

**Which abstractions would make future multimodal/GraphRAG possible
without forcing them into core:** none needed changing — `Module`'s
`forward(input, *, context=None) -> Any` already accepts and returns
arbitrary Python objects, so a future `Document` type carrying
text/image/table content would flow through the exact same `Module`
contract with zero kernel change required. This was independently
verified, not assumed: `Module.forward`'s signature has no type
constraint on `input`/output beyond `Any`.

## 31C — Comparative framework analysis

Research performed directly (via `WebSearch`/`WebFetch` against current
upstream documentation/source, not from training-data memory alone,
after two prior attempts to delegate this research to background
agents failed — one returned a status update instead of real findings,
one stalled/timed out — both discarded, this research was done directly
in this same session instead).

### LangChain (`langchain-core`)
- **Purpose**: general LLM application framework (not RAG-specific).
- **Execution model**: the `Runnable` protocol — every component
  (`prompt | model | parser`) implements `Runnable`, giving a uniform
  sync/async/streaming/batch interface. This is a genuine, mature
  composition primitive, not merely function chaining.
- **Tracing/observability**: `Runnable`s emit a stream of lifecycle
  events (`on_chain_start`, `on_llm_start`, etc.); **LangSmith**, a
  separate hosted (and for scale, paid) product, is the primary
  consumer of these events for actual trace visualization/storage. The
  tracing *hooks* are open-source; the *product* is external.
- **Dependency footprint** (verified directly from `libs/core/pyproject.toml`):
  ~10 required runtime dependencies, including **`langsmith` itself as
  a default dependency** of `langchain-core` — i.e., even the "core"
  package assumes the existence of the hosted tracing product's client
  library.
- **Provider abstraction**: genuinely provider-neutral at the
  `Runnable`/model-interface level (`"openai:gpt-5.5"`-style string
  prefixes switch providers), though provider SDKs still ship as
  separate `langchain-<provider>` packages.
- **Failure semantics, evaluation**: not independently re-verified in
  this pass (time-bounded); LangSmith's evaluation product is the
  primary evaluation story, again external/hosted.

### LlamaIndex (`llama-index-core`)
- **Purpose**: data-framework for LLM applications, RAG-centric.
- **Execution model**: **Workflows** — steps consume/emit typed
  `Event` objects, explicitly event-driven (not a plain chain). This
  naturally maps to OpenTelemetry's span model.
- **Tracing/observability**: an `instrumentation` module ships **inside
  `llama-index-core`** (confirmed: not merely bolted on) — a real
  counterexample to any claim that in-core tracing is unique to
  ragtorch. However, actual trace *backends* (OpenTelemetry, Arize
  Phoenix, Langfuse, MLflow, 15+ others) are external/optional,
  selected via `set_global_handler(...)`.
- **Dependency footprint** (verified directly from PyPI/GitHub):
  **~27 required runtime dependencies** for `llama-index-core` alone,
  including `numpy`, `nltk`, `tiktoken`, `networkx`, `pillow`,
  `sqlalchemy`, `aiohttp` — a substantially heavier "core" than the
  name suggests.
- **Failure semantics**: not documented at a level this audit could
  verify from public docs in the time available — recorded as
  "unverified," not guessed.

### RAGLAB (`fate-ubw/RAGLAB`, EMNLP 2024)
- **Purpose**: explicitly a **research-oriented** framework for **fair
  comparison of RAG algorithms** — not a general application framework.
  Its own paper explicitly criticizes LangChain/LlamaIndex's high-level
  abstractions as "limiting the ability to develop novel algorithms and
  evaluation metrics" — i.e., RAGLAB's own stated differentiator is
  *lower*-level control for research, the opposite direction from
  LangChain/LlamaIndex's abstraction-heavy approach.
- **Component abstraction**: six core classes (`Retriever`, `Corpus`,
  `Generator`, `Instruction Lab`, `Trainer`, `Dataset`/`Metric`) —
  algorithms subclass `NaiveRag` and override `init()`/`infer()`; the
  parent class provides automatic evaluation/interaction modes.
- **Evaluation**: first-class — `inference()` supports an explicit
  "evaluation mode" against 10 standardized benchmarks.
- **Tracing/observability**: no evidence found of a first-class
  trace/span/execution-identity concept.
- **Dependency model**: tightly coupled to HuggingFace Transformers,
  VLLM, Accelerate, DeepSpeed — a training/fine-tuning-capable research
  stack, architecturally very different from a lightweight kernel.
- **Target**: explicitly research, not production.

### Microsoft GraphRAG
- **Purpose**: **not a general RAG framework** — a specific
  indexing+query pipeline that builds an LLM-extracted knowledge graph
  (entities, relationships, hierarchical community summaries via the
  Leiden algorithm) from unstructured text, then answers queries against
  that graph. Fundamentally different in scope from ragtorch, LangChain,
  LlamaIndex, Haystack, or RAGLAB — those are frameworks; GraphRAG is
  closer to a specific algorithm/pipeline product.
- **Execution model**: a named workflow pipeline (`LoadDocuments →
  ChunkDocuments → ExtractGraph/ExtractClaims/EmbedChunks (parallel) →
  DetectCommunities/EmbedEntities → GenerateReports → EmbedReports`),
  extensible via a factory pattern (custom `run_workflow` functions,
  registerable named-workflow pipelines).
- **Failure handling / tracing**: **not documented at a level this
  audit could verify** from the public architecture docs — explicitly
  recorded as unverified rather than guessed.
- **Direct relevance to ragtorch**: confirms precisely the distinction
  the task instruction already asserts — a real Graph RAG
  implementation needs its own entity/relationship/community data model
  and LLM-driven extraction pipeline, entirely unrelated to
  `CompositionGraph`'s execution-wiring DAG. `CompositionGraph` could
  not become "a knowledge graph" by any incremental change; the two
  concepts don't overlap in what they represent.

### Haystack (`haystack-ai`, deepset)
- **Purpose**: production-oriented RAG/LLM pipeline framework.
- **Execution model**: `Pipeline` is explicitly **a directed graph of
  typed `@component`-decorated classes**, closely analogous in shape to
  `CompositionGraph`+`GraphNode`+`Connection`.
- **Fan-in — direct counterexample found**: Haystack's docs explicitly
  describe **"Smart Pipeline Connections"** — "compatible outputs can be
  implicitly combined when connected to a single input" — i.e.,
  **Haystack supports fan-in natively**, exactly the capability
  `CompositionGraph` currently forbids (see 31F). This is the single
  most concrete, actionable comparative finding in this audit.
- **Failure semantics**: documented for async execution — a component
  error cancels and drains sibling in-flight tasks before re-raising,
  preventing orphaned background work; synchronous execution's failure
  behavior is not equivalently documented (a real, if minor, gap in
  Haystack's own docs, noted honestly).
- **Dependency footprint** (verified directly from `pyproject.toml`):
  the **base** `haystack-ai` install (no extras) includes `openai` and
  `posthog` (product analytics/telemetry) as **unconditional runtime
  dependencies** — a concrete, verified example of a "core" package
  that is neither provider-independent nor telemetry-free by default,
  directly contrasting with ragtorch's `dependencies = []`.
- **Tracing**: "primary" integration is Langfuse (external, third-party
  observability platform), not an in-core trace/span model comparable
  to ragtorch's `Trace`/`Span`.

### LangGraph (used as the concrete execution substrate for
"agentic RAG" — see below for why)
- **Execution model**: `StateGraph` — nodes are Python functions
  receiving/returning partial state updates; edges (direct or
  conditional) route control flow; supports **cycles** (not just DAGs),
  parallel execution, and conditional branching.
- **Failure semantics — a real, mature counterexample**: node failures
  are **localized** (the graph structure identifies exactly which node
  failed, its inputs, and which downstream nodes were blocked), and a
  **checkpointing mechanism enables resuming execution from the last
  checkpoint after a failure** — a materially more sophisticated
  failure/recovery story than anything currently in `ragtorch`
  (`ExecutionEngine` records `RunStatus.FAILED` and re-raises
  `ExecutionError`; it has no resumability/checkpoint concept at all).
- **Relevance to "agentic RAG"**: no single dominant, separately-branded
  "Agentic RAG framework" was found during this research — "agentic
  RAG" (self-reflective/corrective/adaptive retrieval) is consistently
  described in current sources as a **pattern implemented on top of
  existing orchestration substrates**, most commonly LangGraph, not a
  distinct framework with its own execution kernel. This itself is a
  meaningful, honestly-reported finding: the "agentic RAG" category
  does not currently have a comparably foundational execution-kernel
  competitor the way LangChain/LlamaIndex/Haystack do.

### Multimodal RAG — `RAG-Anything` (HKUDS, built on `LightRAG`)
- **Purpose**: all-in-one multimodal document processing RAG
  (text/images/tables/equations/charts).
- **Execution model**: a multi-stage pipeline (Document Parsing →
  Content Analysis → Knowledge Graph Construction → Intelligent
  Retrieval) with **concurrent processing of textual and multimodal
  content through dedicated processing pipelines**.
- **Component/content model**: **not** a unified content type — separate
  "modality-aware processing units" (Visual Content Analyzer,
  Structured Data Interpreter, Mathematical Expression Parser, plus an
  extensible plugin mechanism for custom modalities). This is a real,
  concrete data point against assuming a single universal `Document`
  type is the obviously-correct multimodal design — a substantive,
  currently-maintained framework instead chose per-modality specialized
  paths.
- **Provider abstraction**: plain callback functions
  (`llm_model_func`, `vision_model_func`, `embedding_func`) — simpler
  than a formal Protocol/interface hierarchy, but genuinely
  provider-swappable.
- **Dependency footprint**: modular/optional — core install is
  lightweight, format-specific processing (`[image]`, `[text]`, `[all]`)
  is opt-in via extras, matching the same "small core, optional heavy
  extras" philosophy ragtorch already applies (though ragtorch's core
  today has literally zero deps, vs. this framework's "lightweight but
  non-zero" core).

## 31D — Architecture matrix

Legend: ✓ = present as a first-class, in-core property; ~ = present but
external/optional/partial; ✗ = not found / not applicable; **?** =
could not be verified from available public sources in this audit.

| Property | ragtorch | LangChain | LlamaIndex | RAGLAB | GraphRAG | Haystack | RAG-Anything | LangGraph (agentic) |
|---|---|---|---|---|---|---|---|---|
| A. Explicit execution semantics | ✓ (`ExecutionEngine`/`Run`) | ✓ (`Runnable`) | ✓ (`Workflow`/`Event`) | ~ (`inference()` lifecycle) | **?** | ✓ (`Pipeline.run`) | ~ (multi-stage pipeline) | ✓ (`StateGraph`) |
| B. Composition (linear) | ✓ (`Sequential`) | ✓ (LCEL pipe) | ✓ | ✗ (not composition-centric) | ✗ | ✓ | ~ | ✓ |
| C. Graph execution (DAG) | ✓, but **fan-in ≤ 1** | ~ (`RunnableParallel`) | ~ (event graph) | ✗ | ✓ (workflow graph) | ✓, **fan-in supported** | ✓ (multi-stage) | ✓, **cyclic, not just DAG** |
| D. Module/component lifecycle | ✓ (`Module.__init__`/`forward`/registration) | ✓ (`Runnable`) | ✓ (`Workflow` step) | ✓ (`NaiveRag` subclass) | **?** | ✓ (`@component`) | ✓ (modality units) | ✓ (node function) |
| E. Execution-identity/context propagation | ✓ (`ExecutionContext`, nested, nothing global) | ~ (`RunnableConfig` metadata) | ~ (event metadata) | ✗ | **?** | ~ | **?** | ✓ (state object) |
| F. Observability (in-core, zero-dep) | ✓ (`Trace`/`Span`, no OTel dependency) | ✗ (LangSmith external) | ~ (`instrumentation` module in-core, backends external) | ✗ | **?** | ✗ (Langfuse external) | **?** | ~ |
| G. Trace/span model | ✓, vendor-neutral | ~, OTel-adjacent via LangSmith | ✓, OTel-native | ✗ | **?** | ~ | **?** | ~ |
| H. Metrics | ✓ (`MetricsCollector`, in-core) | ~ (via LangSmith) | ~ | ✗ | **?** | ~ | **?** | ~ |
| I. Evaluation as first-class | ✓ (`Evaluator`/`Metric`, model-agnostic) | ~ (LangSmith Evaluation, hosted) | ~ | ✓ (10 benchmarks, automatic eval mode) | ✗ | ~ | **?** | ✗ |
| J. Failure isolation | ✓ (`ExecutionError` wraps + re-raises, no resumability) | **?** | **?** | ✗ | **?** | ✓ (async task draining) | **?** | ✓✓ (localized + **checkpointed resumability** — more mature than ragtorch) |
| K. Provider independence (core has zero vendor deps) | ✓✓ (`dependencies = []`) | ~ (provider-neutral interface, but `langsmith` is a default dep) | ✗ (heavy default deps, though provider-neutral in design) | ✗ (HF/VLLM-coupled) | **?** | ✗✗ (`openai` is a base dependency) | ~ (lightweight core, optional heavy extras) | ~ (part of the LangChain ecosystem) |
| L. Replaceability (swap a component without touching others) | ✓ (Protocol-based, demonstrated in `examples/rag_consumer`) | ✓ | ✓ | ~ (subclassing, less structural) | **?** | ✓ | ✓ (callback functions) | ✓ |
| M. Async readiness | ✗ (not implemented; `Module.__call__` is sync-only) | ✓ | ✓ | **?** | **?** | ✓ (`AsyncPipeline`) | ~ | ✓ |
| N. Serialization readiness | ~ (data model kept serialization-friendly by design, not implemented — A76/step13/16/17 pattern) | ✓ (`RunnableSerializable`) | **?** | **?** | **?** | ✓ ("pipelines are serializable") | **?** | ✓ (checkpointing implies state serialization) |
| O. Multimodal readiness (without polluting core) | ✓ (untyped `Any` payload, verified, unimplemented) | ~ | ~ | ✗ | ✗ | ~ | ✓✓ (this IS its purpose) | ~ |
| P. Graph-RAG readiness (without confusing exec-graph for knowledge-graph) | ✓ (CompositionGraph explicitly ≠ knowledge graph, documented) | ✗ (no native concept) | ~ (has graph-store integrations) | ✗ | ✓✓ (this IS its purpose) | ~ | ~ (has its own KG construction) | ✗ |
| Q. Experiment reproducibility | ~ (deterministic `Run`/`Trace`, no persistence/replay) | ~ (LangSmith run history) | **?** | ✓ (benchmark-driven by design) | **?** | **?** | **?** | ✓ (checkpoint replay) |
| R. Benchmarkability | ~ (this project's own `benchmarks/` convention; no built-in framework benchmark harness) | ~ (LangSmith) | **?** | ✓✓ (10 benchmarks built in, this IS its purpose) | **?** | **?** | **?** | **?** |
| S. Application ergonomics (quick to wire a simple pipeline) | ~ (verified directly: `super().__init__()` required, `Module.__call__` wraps all exceptions as `ExecutionError` — real friction found in `examples/rag_consumer`) | ✓✓ (pipe operator, very low ceremony) | ✓ | ~ (research-oriented, not ergonomics-first) | ✗ (not meant for this) | ✓ | ~ | ~ (more ceremony than LCEL) |
| T. Ecosystem/integrations | ✗ (deliberately none — zero deps) | ✓✓ (largest ecosystem by far) | ✓✓ (large) | ✗ | ✗ | ✓ (moderate, deepset-curated) | ~ | ✓ (LangChain ecosystem) |

## 31E — Differentiation analysis

**Testing the claim**: *"RAG components are executable modules with
explicit composition, execution identity, lifecycle, observability,
failure semantics and evaluation."*

**Verdict: partially true, but NOT uniquely true — every individual
property already exists somewhere in the comparison set.** The claim as
originally phrased would be a false differentiator if asserted without
qualification. The evidence-backed, precise version of what's actually
distinctive:

1. **Zero-dependency, in-core, vendor-neutral observability is
   genuinely rare.** LlamaIndex ships an in-core `instrumentation`
   module (a real counterexample to "nobody else does this in-core"),
   but even LlamaIndex's core has ~27 dependencies and its
   instrumentation is explicitly OpenTelemetry-shaped/adjacent.
   LangChain and Haystack both push tracing to an external, named
   product (LangSmith, Langfuse) as the *primary* recommended path.
   **ragtorch is the only system in this comparison where `Trace`,
   `Run`, and `MetricsCollector` ship in a literally zero-runtime-
   dependency core**, confirmed directly from `pyproject.toml` and
   `trace.py`'s own explicit "does not depend on OpenTelemetry or any
   other observability vendor" design statement.
2. **Provider independence is real but not unique in intent — it is
   unique in degree.** LangChain's `Runnable`/model-string interface is
   also provider-neutral by design; the difference found is that
   LangChain's and Haystack's "neutral" interfaces still ship with
   default dependencies on their own hosted-product client libraries
   (`langsmith`) or, in Haystack's case, a specific vendor SDK
   (`openai`) baked into the base install. **ragtorch's `dependencies =
   []` is a stronger, verified claim than any other system audited.**
3. **The claim's "explicit composition" and "lifecycle" pieces are NOT
   differentiators** — LangChain's `Runnable`, LlamaIndex's `Workflow`,
   Haystack's `@component`/`Pipeline`, and LangGraph's node functions
   all provide comparably explicit composition and lifecycle. No
   honest claim of uniqueness can be made here.
4. **Failure semantics are NOT a differentiator in ragtorch's favor —
   if anything, LangGraph's checkpointed, resumable, localized failure
   model is more mature than ragtorch's current "wrap and re-raise, no
   resumability."** This is recorded honestly as a real gap, not
   glossed over.
5. **Evaluation-as-first-class is shared with RAGLAB**, which was
   purpose-built for exactly this. ragtorch's evaluation framework
   (`Evaluator`/`Metric`, explicitly not `Module`-coupled) is
   comparably general, arguably more so since RAGLAB's evaluation is
   benchmark-dataset-specific by design (research tool) while
   ragtorch's is domain-agnostic (`ExactMatch`, `Latency`, extensible
   `Metric` protocol) — but this is a difference in *scope*
   (general-purpose vs. RAG-research-specific), not a claim that
   ragtorch's evaluation is more capable.

**The precise, defensible differentiation statement**: *ragtorch is a
zero-runtime-dependency execution kernel whose observability
(`Trace`/`Run`/`MetricsCollector`) and evaluation
(`Evaluator`/`Metric`) primitives ship in-core with no vendor coupling
and no assumed hosted product — a combination not found together in any
of the six comparison frameworks audited, each of which either has a
heavier default dependency footprint, couples its core to a specific
provider/telemetry product, or is scoped to a narrower purpose
(algorithm research, knowledge-graph construction, multimodal document
processing) rather than being a general execution substrate.* This is
a narrower, more honest claim than the original hypothesis, and it does
**not** extend to composition expressiveness, failure recovery, or
async readiness, where ragtorch is currently behind the more mature
systems audited (see 31D rows C, J, M).

## 31F — Adversarial alternatives

Eight candidate futures evaluated against the criteria the task
specifies. Evidence-weighted, not feature-counted.

| Candidate | Architectural fit | User value | Differentiation | Complexity | Dependency risk | Provider coupling | API stability | Migration cost | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| A. Execution kernel only (status quo) | Strong — matches every prior step's evidence (A76/A78/A79/A83) | Real but narrow (proven by `examples/rag_consumer`) | Real, precise (31E) | Lowest | None | None | Highest | Zero | **Currently best-supported by evidence** |
| B. Add provider-neutral RAG interfaces (`Retriever`/`Embedder`/etc. as core Protocols) | Weak today — zero real *external* consumer beyond the demo this project wrote itself (same conclusion as A76/A78/A79) | Speculative — would guess at a contract shape | Would dilute, not strengthen, 31E's differentiation | Real jump in surface area | Low if kept Protocol-only | Low if kept Protocol-only | At risk — a wrong early contract is hard to undo pre-1.0 | Real | Rejected — not yet justified |
| C. Separate `ragtorch-rag` package | Premature — nothing to put in it yet | None yet | N/A | Adds packaging/release surface (Step 28's own lesson: even one release pipeline was substantial work) | N/A | N/A | N/A | High (a second package to maintain) | Rejected — no content justifies a second package |
| D. Optional provider packages (`ragtorch[openai]` etc.) | N/A — no provider code exists to make optional | None yet | N/A | N/A | N/A | N/A | N/A | N/A | Rejected — nothing to gate behind an extra |
| E. Full RAG framework (LangChain/LlamaIndex-shaped) | Poor fit — would require abandoning the zero-dependency kernel property that is 31E's actual differentiator | Would compete directly with far larger, better-resourced ecosystems (31D row T) | Would be erased, not created | Very high | Very high | Very high | Would break pre-1.0 repeatedly | Very high | Rejected — evidence argues directly against this |
| F. RAG experimentation/research framework (RAGLAB-shaped) | Plausible fit for `evaluation` package specifically, poor fit for `core` | Real for a narrow research audience | Would compete with RAGLAB's already-established, benchmark-heavy niche without new evidence of demand | High (would need benchmark datasets, algorithm reproductions) | Moderate (HF/eval-dataset dependencies likely) | Moderate | Moderate | Moderate | Rejected — no evidence of research-audience demand; would require becoming what RAGLAB already is |
| G. Execution/observability substrate for RAG (current direction, made explicit) | Strong — this is what 31E's evidence actually supports | Real (proven) | Real (31E) | Low — extends current design, doesn't redirect it | Low | Low | High | Low | **Matches Outcome A; the honest name for what ragtorch already is** |
| H. General AI workflow kernel (not RAG-specific) | Plausible — nothing in `core/` is RAG-specific today (confirmed: no RAG vocabulary anywhere in `src/ragtorch/core/`) | Broader but more diffuse | Would need its own comparison against Airflow/Prefect/Temporal-class systems, entirely unresearched in this audit | Unknown — out of scope | Unknown | Unknown | Unknown | Unknown | **Named but explicitly not evaluated** — real candidate for a *future*, separately-scoped audit, not decided here without dedicated research |

**Selected candidate: G — execution/observability substrate for RAG**,
which is not a change from the status quo (A) but a more precise,
evidence-backed articulation of what A already is, per 31E.

## 31G — Future-change analysis

Applied to Candidate G (the selected direction) and to the one named
concrete gap (`CompositionGraph` fan-in):

1. **Can the implementation be replaced?** Yes — every provider-facing
   piece in `examples/rag_consumer` already demonstrates this
   (Protocol-based `Embedder`/`VectorStore`, swappable `Generator`
   subclasses).
2. **Can it be extended?** Yes, within the kernel's existing
   extension points (`Module` subclassing, `Component` structural
   typing) — no new extension mechanism is proposed or needed.
3. **Can it be tested without a provider?** Yes, proven by
   `examples/rag_consumer`'s 86 tests, all provider-free except two
   explicitly-marked, `openai`-mocked tests.
4. **Can it support async later?** **No evidence either way from this
   audit** — `Module.__call__` is sync-only today (confirmed,
   `inspect.signature`), and no async design work was done in this
   step. Recorded as an open question, not answered.
5. **Can it be serialized later?** Consistent with the project's own
   repeated prior finding (A76/step13/16/17): data shapes are kept
   serialization-friendly by construction (frozen dataclasses,
   `Any`-typed payloads) without serialization itself being built.
6. **Can it be observed?** Yes — this is 31E's central, verified claim.
7. **Can it fail safely?** Yes for the "don't corrupt state, always
   surface the error" sense (`ExecutionError` wrapping, confirmed);
   **no** for the "resume after failure" sense (LangGraph's checkpoint
   model has no ragtorch equivalent) — an honest, named gap.
8. **Can the public API remain stable?** Yes — nothing in this audit
   proposes a public API change.
9. **Can a developer understand it six months later?** The
   `examples/rag_consumer` demo's own documented friction (must call
   `super().__init__()`; `Module.__call__` wraps all exceptions) shows
   this is *learnable but not obvious* — a real ergonomics note (31D
   row S), not a blocker.
10. **Does it introduce provider lock-in?** No — unchanged, zero
    provider code exists.
11. **Does it introduce dependency bloat?** No — zero runtime
    dependencies, unchanged.
12. **Does it make multimodal possible without polluting the core?**
    Yes, verified: `Module.forward`'s `Any`-typed payload already
    accommodates it; RAG-Anything's real-world precedent (31C) shows a
    working multimodal system does NOT require a unified content type
    at the framework level, which is consistent with ragtorch not
    needing to define one either.
13. **Does it make GraphRAG possible without pretending
    `CompositionGraph` is a knowledge graph?** Yes, and GraphRAG's own
    real architecture (31C) confirms the two concepts (execution DAG
    vs. knowledge graph) are unrelated enough that no incremental
    change to `CompositionGraph` could produce a knowledge graph
    regardless.
14. **Can research experiments be reproduced?** Partially — `Run`/
    `Trace` give deterministic in-memory identity for one execution,
    but there is no persistence/replay mechanism (unlike LangGraph's
    checkpointing or RAGLAB's benchmark-dataset-driven reproducibility)
    — an honest gap, not claimed as solved.
15. **Can two RAG architectures be compared fairly?** Only via the
    `evaluation` package's `Evaluator`/`Metric` abstractions, which are
    real and tested but have never been used to compare two *different*
    RAG architectures against each other (only used within
    `examples/rag_consumer` for one architecture's own quality) — an
    honest scope note, not a false claim of proven comparability.

## 31H — Benchmark

`benchmarks/step30_composition_comparison.py` — measures plain Python
function chaining vs. `Sequential` (direct call) vs.
`ExecutionEngine.execute()` at `OFF` vs. `DEBUG` observability, across
1/5/20/50-step pipelines. (Filename kept as `step30_` to match this
task's own numbering as given in the instruction; the evaluation
document itself uses Step 31 to avoid colliding with the existing,
already-merged `step30-evaluation.md` — see the numbering note at the
top of this document.) Actual measured output (this run, no threshold
asserted):

```
shape                                            mean (us)  median (us)
plain python, 1 steps                                 0.66         0.60
Sequential (direct call), 1 steps                    15.63        14.30
ExecutionEngine OFF, 1 steps                         55.43        54.20
ExecutionEngine DEBUG (trace), 1 steps              106.92        85.60

plain python, 50 steps                                3.51         3.20
Sequential (direct call), 50 steps                  382.68       351.05
ExecutionEngine OFF, 50 steps                      1081.04      1058.00
ExecutionEngine DEBUG (trace), 50 steps            1119.71      1113.45
```

(Full 5/20-step rows in the benchmark's own output, omitted here for
brevity — same pattern.)

**Architectural reading, not a performance judgment**: plain Python is,
unsurprisingly, orders of magnitude cheaper — this is expected and
uninteresting on its own. The more informative finding: the gap between
`ExecutionEngine` at `OFF` vs. `DEBUG` observability is small relative
to the gap between `OFF` and no-engine-at-all (`Sequential` direct
call) — meaning most of `ExecutionEngine`'s overhead comes from
`Run`/`EventBus` bookkeeping that happens regardless of observability
level, not from `DEBUG`-level tracing itself. This is useful evidence
for any future work on `ExecutionEngine`'s baseline cost, but does not
by itself justify any change in this step — no consumer has reported
this overhead as a real problem, and the demo's own benchmark
(`examples/rag_consumer/benchmark.py`) already showed embedding cost
(~270ms/batch with a real model) dwarfs this overhead by 3+ orders of
magnitude in the one real workload measured so far.

## 31I — Security review

- No credentials, API keys, or provider secrets were added, used, or
  required anywhere in this audit — all research was documentation
  reading (`WebSearch`/`WebFetch`) and local benchmarking with no
  network calls from `ragtorch` code itself.
- **Provider credential boundaries**: unchanged from `examples/rag_consumer`'s
  existing, already-reviewed design (its own step evaluation §14) —
  `OPENAI_API_KEY` read only via `os.environ.get`, never in source.
- **Trace data sensitivity**: `ragtorch.core.trace.Span.attributes` is
  an open `dict[str, Any]` — confirmed by direct source read that
  nothing in `core/` populates it with retrieved-document content or
  prompts by default (the engine only ever attaches structural
  metadata like span names); this matches the project's existing
  redaction policy (`core/logging.py`'s `redact()`/`is_sensitive_key()`,
  unchanged). No new risk introduced.
- **Document contents in `Run` artifacts**: `Run.output`/`Run.error`
  are `Any`-typed and will contain whatever a `Module`'s `forward()`
  returns/raises — this was already true before this audit and is
  unchanged; a real, pre-existing consideration for any future
  persistence layer (not built here), not a new finding.
- **No paid API calls were made** during this audit — all framework
  research used public documentation/source only.

## 31J — Dependency review

- `ragtorch`'s `dependencies = []` remains unchanged — confirmed
  directly, zero lines touched in `pyproject.toml`.
- This audit's own new files (`benchmarks/step30_composition_comparison.py`,
  this evaluation document) introduce no new dependency.
- The comparative research itself (31C/31D) reinforces treating
  zero-dependency-core as a real architectural asset, per the task's
  explicit framing — verified with concrete numbers (LangChain
  ~10 deps including a hosted-product client library by default,
  LlamaIndex ~27 deps, Haystack's base install includes `openai`
  unconditionally) rather than asserted without evidence.

## 31K — Compatibility review

- Zero changes to `src/ragtorch/**` — confirmed via `git diff --stat
  src/ragtorch/` (empty).
- `ragtorch.__all__` unchanged.
- Existing 549-test suite unaffected — re-run after adding the
  benchmark file, still 549 passed, 13 deselected.
- No changes to `examples/rag_consumer/` — this audit only *read* it,
  never modified it.

## 31L — Recommendation

**Outcome A — no architectural change.** Keep `ragtorch` as an
execution/observability substrate for RAG (Candidate G, 31F) — a more
precise articulation of the existing kernel, not a redirection.

**One concrete, named gap is recorded for future evidence-gathering,
not fixed now**: `CompositionGraph`'s fan-in ≤ 1 restriction blocks a
real, plausible future consumer shape (hybrid dense+sparse retrieval
fusion, as sketched in the task instruction itself) that a comparable
system (Haystack) already supports natively. This is not acted on in
Step 31 because: (a) no real consumer requires it yet — 
`examples/rag_consumer` uses `Sequential`, not `CompositionGraph`, and
does not need fan-in; (b) ADR-016 already recorded this exact
limitation as a deliberate, evidence-gated deferral (not an oversight)
when `CompositionGraph` was designed; (c) designing a fan-in
aggregation semantics without a real consumer to validate the shape
against would repeat exactly the premature-abstraction mistake this
project has consistently and correctly avoided (A11/A61/A76/A78/A79).
**If a real consumer needs hybrid retrieval fusion in the future, this
audit's evidence (Haystack's "Smart Pipeline Connections" precedent,
31C) should be the starting point for that future step's design
comparison — not re-derived from scratch.**

## 31M — Final gate checklist

| # | Gate | Result |
|---|---|---|
| 1 | Repository audit | **PASS** (31A) |
| 2 | Architecture/design | **PASS** (31E/31F — no design change selected, Candidate G is a naming clarification, not a design) |
| 3 | ADR | **NOT APPLICABLE** — no architectural decision was made; Candidate G restates the existing design (ADR-001/005/010/016 etc. remain the governing decisions), it does not supersede them |
| 4 | Public contract | **NOT APPLICABLE** — no contract change |
| 5 | Implementation impact | **NOT APPLICABLE** — zero `src/ragtorch/**` changes, confirmed |
| 6 | Unit tests | **PASS WITH NOTE** — no new unit tests added (correctly, per the task's own instruction: "only add tests if they characterize an important existing behavior discovered during the audit"); the fan-in rejection and `Sequential`'s single-value chain were both characterized via live interpreter tests during the audit itself, not committed as permanent test files, since they duplicate what `tests/unit/core/test_composition.py`/`test_sequential.py` already cover |
| 7 | Integration tests | **PASS** — the existing `examples/rag_consumer` 86-test suite is this audit's real integration evidence, re-confirmed passing, unmodified |
| 8 | Failure/edge cases | **PASS** — `CompositionGraph` fan-in rejection reproduced live against the installed package (31A/31F); this is exactly "testing architectural boundaries, not speculative features" |
| 9 | Benchmark | **PASS** (31H) |
| 10 | Evaluation | **PASS** — this document |
| 11 | CI | **PENDING** — to be verified via real GitHub Actions run before merge, per this project's standing rule (see closure) |
| 12 | Documentation | **PASS** — this document is the primary deliverable |
| 13 | Compatibility | **PASS** (31K) |
| 14 | Security | **PASS** (31I) |
| 15 | Dependencies | **PASS** (31J) |
| 16 | Git diff | **PASS** — reviewed before commit (see closure section) |
| 17 | Evidence-backed final recommendation | **PASS** (31L) |

## Answers to the required success-criteria questions

1. **What exactly is ragtorch?** A zero-runtime-dependency Python
   execution kernel providing explicit composition (`Module`/
   `Sequential`/`Block`/`CompositionGraph`), execution
   identity/lifecycle (`ExecutionContext`/`Run`/`ExecutionEngine`),
   in-core vendor-neutral observability (`Trace`/`Span`/
   `MetricsCollector`), and a general-purpose evaluation framework
   (`Evaluator`/`Metric`).
2. **What exactly is it NOT?** Not a RAG framework with built-in
   providers — no embeddings, vector stores, LLM clients, document
   loaders, chunking, rerankers, multimodal, or GraphRAG code ships in
   it, by design (ADR-005 and repeated, re-confirmed across A76/A78/
   A79/A83).
3. **Who is the target user?** A developer building a RAG (or other
   composable AI-execution) application who wants explicit,
   observable, provider-independent execution without adopting a
   large, opinionated, dependency-heavy framework — demonstrated
   concretely by `examples/rag_consumer`.
4. **What problem does the execution kernel solve?** Giving composed
   components (retriever, reranker, generator, ...) a shared, minimal
   contract for execution identity, observability, and failure
   handling, without dictating what those components actually do or
   which providers they use.
5. **Why use it instead of LangChain?** If zero required dependencies
   and vendor-neutral in-core tracing (not a hosted product) matter
   more than LangChain's much larger ecosystem/integration surface and
   lower-ceremony composition (LCEL's pipe operator) — an honest
   tradeoff, not a strict superiority claim (31D row T, S).
6. **Why use it instead of LlamaIndex?** Same reasoning, plus:
   ragtorch's core has zero dependencies vs. LlamaIndex's ~27 — a
   verified, large, concrete difference.
7. **Why use it instead of RAGLAB?** Different purpose entirely —
   RAGLAB is a research tool for comparing RAG *algorithms* against
   benchmarks; ragtorch is a general execution substrate an application
   (or, in principle, a research tool) could be built on top of. Not a
   competing choice for the same job.
8. **Why use it instead of GraphRAG?** Different purpose entirely —
   GraphRAG is a specific knowledge-graph-construction pipeline/product;
   ragtorch is a general execution kernel. Not a competing choice.
9. **What is genuinely different?** The combination of zero runtime
   dependencies + in-core (not hosted-product-dependent) observability
   + general-purpose evaluation — verified not to co-occur in any of
   the six comparison frameworks audited (31E).
10. **Is that difference useful?** Demonstrated, not merely claimed —
    `examples/rag_consumer` is real evidence the kernel supports a
    working RAG application end-to-end, with the specific friction
    points (fan-in, `Sequential`'s single-value chain,
    `Module.__init__`/`__call__` behaviors) discovered and worked
    around rather than hidden.
11. **Can we demonstrate the difference with the real consumer?**
    Partially — `examples/rag_consumer` demonstrates the kernel
    *works*, but does not yet demonstrate a scenario where a competing
    framework's heavier dependency footprint or external-tracing
    requirement would have been a concrete blocker; that would require
    a second, comparative implementation effort not undertaken in this
    audit.
12. **What should NOT be built?** RAG provider abstractions
    (Retriever/Embedder/VectorStore contracts) without a real external
    consumer (still true, per 31F candidate B); a full competing
    framework (31F candidate E); a research/benchmark framework
    competing with RAGLAB (31F candidate F) without evidence of
    research-audience demand.
13. **What should be built next?** Nothing, per this audit's own
    evidence — Outcome A. If anything is eventually justified, the
    `CompositionGraph` fan-in gap (31L) is the most concretely
    evidenced candidate, gated on a real consumer that needs it.
14. **What should remain optional?** Everything provider-specific,
    unconditionally — reinforced, not changed, by this audit.
15. **What belongs in external adapter packages?** Nothing yet exists
    to move — the question remains correctly premature (31F candidates
    C/D), same conclusion as A78/A79/A83.

---

## Git / CI closure

(Filled in after real GitHub-facing work — branch, PR, CI verification,
merge, post-merge CI — following this project's standing rule that PR
CI and post-merge CI must both be independently verified via the actual
GitHub Actions API, never assumed from local test success.)
