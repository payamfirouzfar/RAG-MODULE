# RAG Consumer Demo

A real, working RAG (retrieval-augmented generation) application built
as an **external consumer** of the published `ragmodel` package —
`pip install ragmodel`, `import ragtorch`. This is not a theoretical
example: every component here actually runs, is tested, and is
executed through `ragtorch.ExecutionEngine`.

**Nothing in this directory is part of the `ragtorch` package.** All of
scraping, chunking, embeddings, the vector store, reranking, prompt
construction, and LLM generation are application-level code that
compose on top of `ragtorch.Module`/`Sequential`/`ExecutionEngine`,
exactly as any external user of the published library would build
their own RAG system.

## What ragtorch is not shipping

The `ragtorch` core kernel does not ship embeddings, vector databases,
LLM providers, document loaders, a chunking framework, rerankers, or
multimodal/vision providers — see the main repository's README. This
demo exists specifically to prove that a real RAG application *can* be
built entirely at the application layer on top of `ragtorch`'s
execution/composition primitives, without any of that functionality
needing to live inside the kernel.

## Architecture

```
Query
  │
  ▼
Retriever(Module)       <- embeds query, searches vector store
  │
  ▼
Reranker(Module)        <- optional, can be None
  │
  ▼
PromptBuilder            <- plain function, not a Module (no execution
  │                          state to track; see "Design notes" below)
  ▼
Generator(Module)        <- offline extractive OR real LLM call
  │
  ▼
Answer + Sources
```

Composed with `ragtorch.Sequential`, executed through
`ragtorch.ExecutionEngine` to capture `Run`/`Trace`/`Metrics`.

### Design notes

**Why `Sequential`, not `Block`/`CompositionGraph`.** Verified directly
against the installed `ragmodel==0.5.0` package
(`inspect.getsource(Sequential.forward)`) before choosing: `Sequential`
is a strict `value = step(value)` chain. Every stage in this pipeline
needs both the original question and the accumulating retrieval/prompt
state, which doesn't fit a bare single-value chain without forcing
tuple-unpacking in every step. The fix used here: every stage's
`Module` receives and returns a single immutable `PipelineState`
dataclass (`src/pipeline.py`) — the RAG-equivalent of threading an
accumulator through `Sequential`'s existing contract. `Block`/
`CompositionGraph` were considered and rejected: this is a strictly
linear five-stage pipeline with no branching or fan-in/fan-out, so the
DAG/typed-port machinery those provide would add real complexity for
zero benefit here.

**Why `PromptBuilder` is a plain function, not a `Module`.** It has no
meaningful execution lifecycle of its own worth tracing separately (it
is a pure string-formatting step) — wrapping it as a `Module` was
considered and rejected as unnecessary ceremony; it is called from
inside `PromptStage(Module)` instead, which does carry execution
identity through `ExecutionEngine`.

**Verified `Module` initialization.** Every `Module` subclass here
calls `super().__init__()` as the first line of `__init__` — confirmed
against the installed package's real constructor contract via
`inspect.signature(Module.__init__)` before writing any subclass
(`Module.__init__(self) -> None` takes no arguments; skipping the
`super().__init__()` call means `self._modules` never gets created,
which silently breaks child-`Module` registration in `__setattr__`).
`tests/test_retriever.py::test_retriever_initializes_module_state_correctly`
and the equivalent test in `test_generator.py` guard against
regressing this.

**A real, verified `Module.__call__` behavior worth knowing.** Every
`Module.__call__` — not only calls routed through `ExecutionEngine` —
catches any exception raised inside `forward()` and re-raises it
wrapped as `ragtorch.ExecutionError` (verified via
`inspect.getsource(Module.__call__)` against the installed package).
Calling `.forward()` directly bypasses this wrapping. Both call styles
are exercised in `tests/test_generator.py` and `tests/test_pipeline.py`
so this distinction is tested, not assumed.

## Installation

### Local

```bash
cd examples/rag_consumer
python -m venv .venv
.venv/Scripts/activate   # Windows; source .venv/bin/activate on Unix/macOS
pip install -r requirements.txt
```

### Google Colab

Open `notebook/rag_consumer_colab.ipynb` in Colab. The first cell
installs everything needed — no repository checkout required, no local
files needed beyond what the notebook itself creates.

## Dataset creation

Two modes:

- **SCRAPE MODE**: `build_dataset()` fetches a fixed, bounded list of
  public documentation URLs (default: 5 pages from
  `docs.python.org`), respecting `robots.txt`, using a descriptive
  User-Agent, bounded timeouts, and an inter-request delay. Raw HTML is
  cached locally so re-running never re-fetches an already-cached page.
- **OFFLINE DATASET MODE**: `load_dataset()` reads an already-saved
  `data/documents.jsonl` with zero network access.

Dataset schema (`data/documents.jsonl`, one JSON object per line):

```json
{
  "document_id": "a1b2c3d4e5f6...",
  "url": "https://docs.python.org/3/tutorial/introduction.html",
  "title": "3. An Informal Introduction to Python",
  "text": "cleaned, boilerplate-stripped page text...",
  "retrieved_at": "2026-08-18T12:00:00+00:00"
}
```

`document_id` is a deterministic hash of the URL — the same URL always
produces the same ID, independent of scrape time or content.

## Configuration

One configuration object, `src/config.py`'s `Config` dataclass. Nothing
is scattered through the notebook or the other modules:

```python
CONFIG = Config(
    urls=[...],
    chunk_size=800,
    chunk_overlap=120,
    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
    vector_store_backend="faiss",  # or "in_memory"
    top_k=5,
    rerank=False,
    mode="offline",  # or "llm"
)
```

## Embedding model replacement

`Embedder` (`src/embeddings.py`) is a `Protocol` — any implementation
satisfying `embed_documents(texts) -> vectors` and
`embed_query(text) -> vector` works, without changing `Retriever`,
`VectorStore`, or the pipeline at all. Two implementations ship:
`SentenceTransformersEmbedder` (real, requires the optional
`sentence-transformers` dependency) and `HashingEmbedder`
(dependency-free, deterministic, used in unit tests and to
demonstrate replaceability). The notebook's "Provider replacement"
section swaps between them live.

## Vector store replacement

Same pattern: `VectorStore` is a `Protocol`
(`add`/`search`/`save`/`load`). `FaissVectorStore` (real, FAISS-backed)
and `InMemoryVectorStore` (dependency-free, used in unit tests) both
satisfy it.

## LLM configuration

`MODE="llm"` with `LLM_PROVIDER="openai"` (the only provider
implemented in this initial demo) calls a real LLM. The API key is
read from the `OPENAI_API_KEY` environment variable or a Colab
Secret — **never** from notebook source or a config file. If no key is
configured, `LLMGenerator` raises a clear `GeneratorError` explaining
what to set; it never falls back silently.

```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY=sk-...
```

In Colab, use the Secrets panel (key icon in the left sidebar) instead
of a code cell.

## Offline mode

`MODE="offline"` (the default) uses `OfflineGenerator`: a deterministic
extractive generator (no LLM, no API key, no network) that returns the
highest-scored retrieved chunk as the answer, or an explicit
"insufficient evidence" message when nothing relevant was retrieved.
The entire notebook, including evaluation, runs end-to-end in this mode
with zero external services — this is what CI exercises.

## Evaluation

`src/evaluation.py` — a **small, explicitly-labeled application-level
smoke/evaluation dataset**, not a scientific RAG benchmark. Measures
retrieval hit@1, hit@k, mean reciprocal rank (MRR), and citation
presence across at least 10 questions, including **negative questions**
whose answers are not present in the dataset — the system is expected
to say the evidence is insufficient, not guess.

## Limitations

- The default dataset (5 Python documentation pages) is small; hit@k
  and MRR numbers reported by the notebook reflect that small corpus,
  not general RAG quality.
- `OfflineGenerator` is extractive, not abstractive — it returns the
  top retrieved chunk's text, not a synthesized answer. Real answer
  synthesis requires `MODE="llm"`.
- Only OpenAI is implemented as an LLM provider in this initial demo;
  `LLMGenerator`'s structure supports adding others (the `_provider`
  check in `generator.py` is the extension point).
- Reranking (`Reranker` in `reranker.py`) uses a simple deterministic
  lexical-overlap heuristic, not a real cross-encoder model — this
  keeps the demo dependency-light; swapping in a real reranker model
  would follow the exact same replaceable-component pattern as the
  embedder.
- No multimodal or Graph RAG support — explicitly out of scope, see
  below.
- **`min_score` filtering is embedder-dependent, tested honestly, not
  overclaimed.** `Retriever`'s `min_score` threshold (`src/retriever.py`)
  is what allows negative/unanswerable questions to correctly produce
  "insufficient evidence" instead of an answer extracted from an
  irrelevant chunk — verified directly during this demo's own
  development: with `HashingEmbedder` (the dependency-free fallback
  used in unit tests), word-hash collisions inflate cosine similarity
  across nearly all pairs of text, so `min_score` does not reliably
  discriminate relevant from irrelevant content with that embedder.
  With `SentenceTransformersEmbedder` (genuine semantic embeddings,
  what the actual Colab notebook uses), similarity scores are far more
  discriminative and `min_score` behaves as intended — **actually run**
  (not assumed) against a 5-document sample corpus with
  `all-MiniLM-L6-v2`: 5 positive questions scored **hit@1 = 100%, MRR =
  1.000**, and **both** negative (unanswerable) questions were
  correctly flagged as insufficient evidence (**2/2, 100%** negative-
  question correctness). Unit tests
  (`tests/test_retriever.py::test_retriever_min_score_filters_low_scoring_results`)
  use carefully chosen text to demonstrate the mechanism works
  correctly even with `HashingEmbedder`, but do not claim it is
  reliable with that embedder on arbitrary real-world queries — the
  numbers above, from the real embedder, are what the Colab notebook's
  own evaluation section should be expected to reproduce (exact numbers
  will vary with the actual `docs.python.org` dataset scraped live).

## Security

- No API key appears anywhere in this repository's source, tests, or
  notebook cells — only read via `os.environ.get("OPENAI_API_KEY")` or
  Colab Secrets.
- The scraper respects `robots.txt`, uses bounded timeouts, an
  inter-request delay, a descriptive User-Agent, and refuses to exceed
  `max_pages` — it cannot be used as an unrestricted crawler.
- No credential of any kind is committed anywhere in this directory —
  confirmed by a manual secret-pattern scan before this demo was
  committed (see the top-level evaluation ledger for this task).

## Future work (explicitly not implemented here)

- **Multimodal**: application boundaries are designed so a future
  `Document`-like type could carry `text`/`image`/`document` content
  without changing the `ragtorch` kernel at all — this demo's
  `Document`/`Chunk` types are intentionally simple (`text: str`) and
  would need extension, not a kernel change, to support this.
- **Graph RAG**: not implemented. `ragtorch.CompositionGraph` is an
  execution/composition graph (how `Module`s are wired for execution),
  **not** a knowledge graph — a real Graph RAG implementation would
  need its own entity/relationship/traversal data model, entirely
  separate from `CompositionGraph`, and is out of scope for this demo.
