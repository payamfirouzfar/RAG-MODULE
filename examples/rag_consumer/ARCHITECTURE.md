# RAG Consumer Demo — Architecture

## Data flow

```
                    ┌─────────────────────┐
                    │   Fixed URL list      │
                    │   (config.py)          │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   scraper.py           │  bounded, robots.txt-respecting,
                    │   (WEB SCRAPING)       │  cached, timeouts, delay
                    └──────────┬───────────┘
                               │ raw HTML
                    ┌──────────▼───────────┐
                    │   dataset.py           │  clean_html(), deterministic
                    │   (CLEANING)           │  document_id, documents.jsonl
                    └──────────┬───────────┘
                               │ list[Document]
                    ┌──────────▼───────────┐
                    │   chunking.py          │  configurable chunk_size /
                    │   (CHUNKING)           │  chunk_overlap
                    └──────────┬───────────┘
                               │ list[Chunk]
                    ┌──────────▼───────────┐
                    │   embeddings.py        │  Embedder Protocol:
                    │   (EMBEDDINGS)         │  SentenceTransformersEmbedder |
                    └──────────┬───────────┘  HashingEmbedder
                               │ vectors
                    ┌──────────▼───────────┐
                    │   vector_store.py      │  VectorStore Protocol:
                    │   (VECTOR INDEX)       │  FaissVectorStore | InMemoryVectorStore
                    └──────────┬───────────┘
                               │
      ═══════════════════════ ragtorch.Sequential ═══════════════════════
                               │
         query ──────► ┌──────▼───────┐
                        │ RetrieveStage │  wraps retriever.py's Retriever(Module)
                        │  (Module)      │  embed query -> vector_store.search()
                        └──────┬───────┘         -> RetrievalResult[]
                               │ PipelineState
                        ┌──────▼───────┐
                        │ RerankStage   │  wraps reranker.py's Reranker(Module)
                        │  (Module)      │  optional -- reranker=None is a first-
                        └──────┬───────┘  class supported path
                               │ PipelineState
                        ┌──────▼───────┐
                        │ PromptStage   │  calls prompt_builder.py's
                        │  (Module)      │  build_prompt() -- separate component,
                        └──────┬───────┘  not buried in the generator
                               │ PipelineState
                        ┌──────▼───────┐
                        │ GenerateStage │  wraps generator.py's Generator(Module):
                        │  (Module)      │  OfflineGenerator (extractive, no LLM) |
                        └──────┬───────┘  LLMGenerator (real OpenAI call)
                               │
      ══════════════════════════ ExecutionEngine ══════════════════════════
                               │ ExecutionResult (Run/Trace/Metrics)
                    ┌──────────▼───────────┐
                    │  Answer + Sources      │
                    │  (PipelineResult)       │
                    └──────────┬───────────┘
                               │
                    ┌──────────▼───────────┐
                    │   evaluation.py         │  hit@1, hit@k, MRR,
                    │   (RAG EVALUATION)     │  citation presence,
                    └──────────────────────┘  negative-question correctness
```

## Component ownership

| Layer | Owns | Package |
|---|---|---|
| Execution/composition | `Module`, `Sequential`, `ExecutionEngine`, `Run`/`Trace`/`Metrics` | `ragtorch` (published as `ragmodel`) |
| Everything else | scraping, cleaning, chunking, embeddings, vector store, retrieval, reranking, prompting, generation, evaluation | `examples/rag_consumer` (this demo, application-level) |

**"The RAG application owns provider selection; ragtorch owns
execution."** — every provider decision (which embedding model, which
vector store, which LLM) is made in this demo's own code
(`config.py`/`embeddings.py`/`vector_store.py`/`generator.py`).
`ragtorch` never imports, requires, or knows about any of them; it only
executes whatever `Module`s this demo hands it.

## Why `PipelineState`, not raw values, flows through `Sequential`

`Sequential.forward()` is a strict `value = step(value)` chain (verified
against the installed package, not assumed — see the README's "Design
notes"). This pipeline's stages need both the original question and the
accumulating retrieval/prompt state, so each stage receives and returns
one immutable `PipelineState` dataclass rather than forcing tuple
unpacking at every step.

## CompositionGraph vs. Graph RAG — explicitly not the same thing

`ragtorch.CompositionGraph` is a generic, immutable execution/composition
DAG for wiring `Module`s together (nodes + connections, fan-in ≤1,
acyclic) — it describes *how components execute*, not *what the
retrieved corpus knows*. A real Graph RAG implementation would need its
own entity/relationship/knowledge-graph data model and graph-aware
retrieval semantics, entirely separate from `CompositionGraph`. This
demo does not implement Graph RAG and does not use `CompositionGraph`
at all (the pipeline is strictly linear — see the README's "Design
notes" for why `Sequential` was chosen over `Block`/`CompositionGraph`).
