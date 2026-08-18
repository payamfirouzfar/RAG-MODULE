# Step 30 Evaluation — Real External RAG Consumer/Validation Application

## Status

**Step 30: COMPLETE.** A real, tested, end-to-end RAG application
(`examples/rag_consumer/`) was built as an external consumer of the
published `ragmodel==0.5.0` package. Zero changes to `src/ragtorch/**`.

This is not "Step 30" of the RAG-MODULE architecture project's normal
step sequence — per the task instruction's explicit "Do not begin a new
architectural step after completing this task," this document uses the
next available step number purely to slot into this project's existing
evaluation-ledger naming convention, not to claim continuation of the
17-gate architectural step sequence (Steps 1-29).

## Objective

Build a real, working RAG consumer application on top of the published
`ragmodel` package, proving the published library actually works as a
real external user would use it — not a theoretical example.

---

## 1. Repository audit

- `git rev-parse HEAD` / `origin/main`: both `e13e728c9aa10419e6bf35dbb0761f8cd5b56953`,
  confirmed identical (matching the task instruction's stated SHA).
- `git status`: clean before starting (one unrelated untracked scratch
  file, `my_rag.py`, predating this task).
- `pytest -q` (existing suite): **549 passed, 13 deselected** — run
  before touching anything.
- Installed the **actual published package** (`pip install
  ragmodel==0.5.0` into a fresh venv, not the dev checkout) and
  inspected the real API via `inspect.signature`/`inspect.getsource`,
  not assumption:
  - `Module.__init__(self) -> None` — no arguments; confirmed
    `Module.__setattr__` requires `self._modules` (set up by
    `__init__`) to exist before it will register a child `Module`,
    meaning every subclass **must** call `super().__init__()` first.
  - `Module.__call__(self, input, *, context=None)` — **every** call
    (not only via `ExecutionEngine`) catches any exception raised
    inside `forward()` and re-raises it wrapped as
    `ragtorch.ExecutionError` (with the original attached via
    `__cause__`); `.forward()` called directly bypasses this wrapping.
    This was discovered by running the real test suite (see §6 below),
    not assumed from documentation.
  - `Sequential.__init__(self, *steps: Module)`, and — critically —
    `Sequential.forward()`'s exact source read directly: a strict
    `value = step(value)` chain, confirmed via
    `inspect.getsource(Sequential.forward)` before any pipeline design
    decision was made.
  - `ExecutionEngine(level=ObservabilityLevel.BASIC).execute(module,
    input, context=None) -> ExecutionResult` with `.run`/`.trace`/
    `.metrics` fields, `.output` property.
  - `RunStatus` members: `PENDING/RUNNING/SUCCEEDED/FAILED/CANCELLED`.
  - `Evaluator(metrics, *, configuration_hash=None).evaluate(system,
    cases) -> EvaluationResult`; `EvaluationCase(input, expected=None,
    name=None, metadata=...)`.
  - Full `ragtorch.__all__` (60 names) enumerated directly.
  - A live `Retriever`→`Generator` `Sequential` composition, executed
    through both direct call and `ExecutionEngine`, confirmed working
    against the real installed artifact before any application code
    was written.

## 2. Architecture/design

See `examples/rag_consumer/README.md`'s "Design notes" and
`ARCHITECTURE.md` for the full record. Key decisions, each with
evidence:

- **`Sequential`, not `Block`/`CompositionGraph`.** Chosen only after
  reading `Sequential.forward`'s real source (§1) and confirming the
  pipeline's actual data-flow need (every stage needs both the original
  question and accumulating state). Solved by threading a single
  immutable `PipelineState` dataclass through `Sequential`'s existing
  single-value contract, rather than forcing tuple-unpacking or
  reaching for `CompositionGraph`'s heavier DAG/port machinery for what
  is a strictly linear 4-stage chain.
- **`PromptBuilder` is a plain function, not a `Module`.** No
  meaningful execution lifecycle of its own to trace separately;
  wrapping it would have been unnecessary ceremony. Called from inside
  `PromptStage(Module)`, which does carry execution identity.
- **Reranking is optional by construction**, not a special case:
  `maybe_rerank(reranker, ...)` with `reranker=None` is the tested
  default path (`build_pipeline(..., reranker=None, ...)`).
- **`min_score` filtering added to `Retriever`** (application-level,
  not `ragtorch`) after discovering during real testing (§8) that a
  plain nearest-neighbor vector search always returns its `top_k`
  closest matches even when none are relevant — necessary for negative
  questions to be correctly flagged as "insufficient evidence" rather
  than answered from an irrelevant chunk.

## 3. ADR

**No ADR was created in `src/ragtorch/`** — correctly, per the task
instruction's explicit rule: an ADR is required only if the *core
library's* architecture changes, and it did not. All design decisions
above are documented in the demo's own README/ARCHITECTURE.md, not as
ragtorch ADRs.

## 4. Public contract

`examples/rag_consumer/src/`'s own internal contracts (not ragtorch's):
`Embedder`/`VectorStore` Protocols (`embed_documents`/`embed_query`,
`add`/`search`/`save`/`load`), `Retriever(Module)`/`Reranker(Module)`/
`Generator(Module)` subclasses, `PipelineState` value object,
`Document`/`Chunk`/`RetrievalResult` frozen dataclasses. Documented in
`README.md` and `ARCHITECTURE.md`.

## 5. Implementation

All application code lives under `examples/rag_consumer/src/` —
confirmed via `git status --short` and `git diff --stat src/ragtorch/`
that **zero** files under `src/ragtorch/` changed. Files: `config.py`,
`scraper.py`, `dataset.py`, `chunking.py`, `embeddings.py`,
`vector_store.py`, `retriever.py`, `reranker.py`, `prompt_builder.py`,
`generator.py`, `pipeline.py`, `evaluation.py`.

## 6. Unit tests

`examples/rag_consumer/tests/` — **86 tests**, all passing, run against
the real installed `ragmodel==0.5.0` package (not the dev checkout of
`ragtorch`):

```
86 passed in ~2-10s (varies with openai installed or not)
```

Real discovery made while writing these tests (not assumed): five tests
initially failed with `ModuleNotFoundError: No module named 'openai'`
missing or `GeneratorError` vs. `ExecutionError` mismatches — root
cause traced to `Module.__call__`'s real exception-wrapping behavior
(§1), which my first test draft had wrongly assumed matched only
`ExecutionEngine`'s behavior. Fixed by testing both `.forward()` (raw
`GeneratorError`) and `__call__`/`generator(...)` (wrapped
`ExecutionError`) explicitly, verified against the actual installed
package, not guessed.

Coverage by category (all requested in the task instruction):
scraper (successful page, timeout, HTTP error, malformed HTML, empty
content, robots.txt, caching, max_pages bound), chunking (empty, short,
long, overlap, deterministic IDs, metadata preservation), dataset (HTML
cleaning, deterministic document IDs, save/load round-trip, Unicode),
embeddings (dimension consistency, doc/query shape), vector store
(insert, search, ordering, top-k, empty store, mismatched lengths,
save/load), retriever (top-k, ordering, metadata, empty results,
`min_score` filtering, `Module` initialization regression guard),
reranker (enabled/disabled, preserves-all-results, empty input), prompt
builder (question/context inclusion, anti-hallucination instruction,
citation instruction, no-evidence case), generator (offline mode, LLM
mode mocked success/failure, missing API key, unsupported provider,
`Module` initialization regression guard), pipeline (successful
end-to-end via real `ExecutionEngine`, reranker enabled, empty
retrieval, generator failure propagation as `ExecutionError`,
immutability), citations (every source maps to a retrieved result, no
fabrication, count never exceeds retrieved count), evaluation (hit@1,
hit@k, MRR, citation presence, negative-case detection, summary
rendering).

## 7. Integration/contract tests

The pipeline tests (`test_pipeline.py`) are integration tests in the
real sense: they run the complete `Retriever → Reranker → PromptBuilder
→ Generator` chain through the actual, installed `ragtorch.Sequential`
and `ragtorch.ExecutionEngine`, asserting on real `RunStatus` and a real
rendered `Trace` — not mocked ragtorch internals.

## 8. Failure/edge-case tests

Covered directly: empty corpus/retrieval (insufficient-evidence path),
missing API key (`GeneratorError`), provider failure (mocked, both raw
and `ExecutionError`-wrapped), malformed HTML, HTTP errors, scrape
timeouts, robots.txt disallow, mismatched vector/chunk counts,
overlap ≥ chunk_size validation, immutable `PipelineState`. Real,
non-mocked discoveries made during this work (not hypothetical):
`Module.__call__`'s universal exception-wrapping (§1/§6), and
`HashingEmbedder`'s low discriminative power (§9) leading to the
`min_score` design addition (§2).

## 9. Benchmark

`examples/rag_consumer/benchmark.py`, run twice — once with
`HashingEmbedder` (no model download), once with the real
`SentenceTransformersEmbedder` (`--real-embedder` flag). Actual
measured output:

**HashingEmbedder (dependency-free):**
```
chunking                       mean=    0.025ms  median=    0.023ms
embedding                      mean=    1.639ms  median=    1.642ms
indexing                       mean=    0.082ms  median=    0.074ms
retrieval                      mean=    0.092ms  median=    0.084ms
complete pipeline (offline)    mean=    0.160ms  median=    0.139ms
```

**Real SentenceTransformersEmbedder (`all-MiniLM-L6-v2`):**
```
chunking                       mean=    0.027ms  median=    0.025ms
embedding                      mean=  272.173ms  median=  267.759ms
indexing                       mean=    0.923ms  median=    0.678ms
retrieval                      mean=    8.131ms  median=    7.975ms
complete pipeline (offline)    mean=    9.000ms  median=    8.860ms
```

No hard threshold asserted, matching `ragtorch`'s own established
benchmark discipline. Embedding dominates real-world latency by roughly
two orders of magnitude over every other stage — expected, and now
measured rather than assumed.

## 10. Evaluation (RAG quality)

A small, explicitly-labeled application-level smoke/evaluation dataset
(`src/evaluation.py`), **not a scientific RAG benchmark** — stated as
such in the code, README, and this document. Two real runs:

**With `HashingEmbedder`** (6 eval cases, including 1 negative
question): hit@1 40%, hit@k 100%, MRR 0.700, citation presence 100%,
**negative-question correctness 0%** — the negative question was
incorrectly answered, an honest finding directly attributable to
`HashingEmbedder`'s known weakness (word-hash collisions inflate
similarity scores broadly), documented in the README's Limitations
section rather than hidden.

**With the real `SentenceTransformersEmbedder`** (7 eval cases,
including 2 negative questions, `min_score=0.2`): **hit@1 100%, hit@k
100%, MRR 1.000, citation presence 71.43%, negative-question
correctness 100%** (2/2). This is the number the actual Colab notebook
(which uses the real embedder) should be expected to reproduce.

## 11. CI

Added a **dedicated, isolated job** (`rag-consumer-demo`) to the main
repository's `.github/workflows/ci.yml`, deliberately separate from the
`test`/`packaging` jobs so it cannot slow or destabilize the core
matrix. Installs `ragmodel==0.5.0` (the published package) plus
lightweight demo dependencies (`requests`, `beautifulsoup4`, `openai`)
— **deliberately excludes** `sentence-transformers`/`faiss-cpu` (heavy,
would slow CI for no benefit since unit tests use `HashingEmbedder`/
`InMemoryVectorStore`). Runs the demo's 86-test suite plus
`benchmark.py`. No API keys, no live websites, no GPU, no paid
services — confirmed by direct inspection of every test file for
`@patch`/`monkeypatch` usage on every network/LLM call site.

YAML syntax validated (`yaml.safe_load`). Core repository's own tests
re-confirmed unaffected: **549 passed, 13 deselected**, unchanged.

## 12. Documentation

`examples/rag_consumer/README.md` (installation, architecture, design
notes, configuration, embedding/vector-store replacement, LLM
configuration, offline mode, evaluation, limitations, security, future
multimodal/Graph RAG work) and `ARCHITECTURE.md` (data-flow diagram,
component ownership table, `CompositionGraph`-vs-Graph-RAG
clarification). `notebook/rag_consumer_colab.ipynb` — 19 sections,
matching the task instruction's exact required structure, every code
cell verified syntactically valid Python (`compile()`-checked, 0
errors across 41 cells) and lint-clean (`ruff check`/`ruff format
--check` both pass on the whole `examples/rag_consumer/` tree).

## 13. Compatibility review

- Zero changes to `src/ragtorch/**`, `ragtorch.__all__`, or any
  existing ragtorch test — confirmed via `git diff --stat
  src/ragtorch/` (empty output).
- Core repository's own 549-test suite re-run and unaffected.
- The one modified file outside `examples/` is
  `.github/workflows/ci.yml` (a new, isolated job — the existing `test`
  and `packaging` jobs are byte-for-byte unchanged, confirmed via
  `git diff` review before commit).
- `ragtorch`'s own runtime dependency list (`pyproject.toml`) is
  unchanged — confirmed directly; all demo dependencies live in
  `examples/rag_consumer/requirements.txt` only.

## 14. Security review

- **No API key anywhere in source, tests, or notebook cells** —
  confirmed by a direct regex scan
  (`sk-[a-zA-Z0-9]{15,}|AKIA[0-9A-Z]{16}|api[_-]?key\s*=\s*[...]`)
  across every `.py`/`.md`/`.ipynb`/`.txt` file in
  `examples/rag_consumer/`: zero matches. The one `sk-test-...` string
  in `test_generator.py` is an explicitly fake mock value used only
  with `monkeypatch`/mocked HTTP clients, never a real credential.
- `OPENAI_API_KEY` is read exclusively via `os.environ.get(...)` — the
  notebook documents Colab Secrets as the intended mechanism, never a
  code cell.
- Scraper respects `robots.txt` (real `RobotFileParser` check before
  every fetch), uses a descriptive User-Agent, bounded timeouts, an
  inter-request delay, and refuses (`ScrapeError`) to exceed
  `max_pages` — cannot be used as an unrestricted crawler.
- `__pycache__` directories confirmed gitignored (inherited from the
  main repository's existing `.gitignore`).

## 15. Dependency review

`examples/rag_consumer/requirements.txt` contains `ragmodel==0.5.0`,
`requests`, `beautifulsoup4`, `sentence-transformers`, `faiss-cpu`,
`openai` (optional, LLM mode only), `pytest` — **all scoped to this
demo directory only**. `ragtorch`'s own `pyproject.toml`
`dependencies = []` is unchanged, confirmed directly. No RAG-specific
dependency was added to the core package.

## 16. Git diff review

`git status --short` before commit:
```
 M .github/workflows/ci.yml
?? examples/
```
(`my_rag.py`, an unrelated pre-existing personal scratch file, remains
untracked and excluded from this diff.) `git diff --stat
src/ragtorch/`: empty — zero production library changes. Every new file
under `examples/rag_consumer/` was written specifically for this task;
no generated artifacts, no secrets (§14), no debug code left in.

## 17. Closure

All 17 gates addressed with concrete evidence above. Proceeding to
commit and CI verification.

---

## What was actually tested vs. mocked vs. not tested

**Actually executed, real evidence:**
- Real installed `ragmodel==0.5.0` package (`inspect.signature`/
  `inspect.getsource` against it directly).
- Real `ragtorch.Sequential`/`Module`/`ExecutionEngine` execution
  (86 passing tests, all against the installed package).
- Real `SentenceTransformersEmbedder` (`all-MiniLM-L6-v2`, real model
  download and inference) — embedding, retrieval, full pipeline,
  evaluation (hit@1=100%, MRR=1.0, negative-question correctness=100%
  on a 5-document sample corpus).
- Real benchmark measurements (both `HashingEmbedder` and the real
  embedder).
- Real lint/format checks (`ruff check`/`ruff format --check`) on every
  Python file and every notebook code cell.

**Mocked (explicitly, for CI/unit-test determinism):**
- `requests.get` in all scraper tests (no live network in unit tests).
- OpenAI's `chat.completions.create` in `LLMGenerator` tests (no real
  API key, no real network call).

**What used the network:** only the real-embedder smoke test run
during this task's own development (downloading
`all-MiniLM-L6-v2` from Hugging Face) — not part of the automated test
suite or CI.

**What used an LLM:** nothing in this task's automated evidence. `MODE
="llm"`/`LLMGenerator` is implemented and unit-tested with a mocked
OpenAI client, but no real OpenAI API call was made (no API key exists
in this environment) — this is explicitly not claimed as tested with a
real LLM.

**What used local embeddings:** the real-embedder smoke test (above).

**What was NOT tested:**
- The actual Google Colab runtime itself — the notebook's cells were
  verified for syntax validity and lint cleanliness, and every
  underlying operation was verified via equivalent local Python
  scripts, but the notebook was not executed inside an actual Colab
  environment (no Colab access from this environment).
- Real web scraping of the actual `docs.python.org` URLs configured in
  `CONFIG.urls` (all scraper tests use mocked `requests.get`) — the
  scraper's logic (robots.txt check, caching, cleaning) is tested, but
  a live fetch of those exact pages was not performed in this task.
- A real OpenAI API call (`MODE="llm"`) — mocked only, no API key
  available.
- FAISS-backed retrieval specifically (`InMemoryVectorStore` used for
  all automated tests/benchmarks; `FaissVectorStore`'s logic mirrors it
  closely but was not separately exercised with the real `faiss-cpu`
  library in this task).

## Future work (explicitly out of scope, not attempted)

- Multimodal support, Graph RAG — see `ARCHITECTURE.md` and README's
  "Future work" section; deliberately not implemented per the task
  instruction.
- Additional LLM providers beyond OpenAI.
- A real cross-encoder reranker model (current `Reranker` is a
  deterministic lexical-overlap heuristic).
