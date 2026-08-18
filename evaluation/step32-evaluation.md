# Step 32 Evaluation — BM25 + Reciprocal Rank Fusion Retrieval Primitives

## Status

**Step 32: local implementation, testing, and integration COMPLETE.**
BM25 and RRF shipped as `ragtorch.retrieval`; the real external
consumer (`examples/rag_consumer/`) demonstrably performs dense +
lexical hybrid retrieval using them, unmodified from the existing
`Retriever`/`Chunk`/`RetrievalResult`/`VectorStore` contracts. Zero
runtime dependencies added. `CompositionGraph`/`ExecutionEngine`/
`Sequential`/async execution untouched. Git/CI closure (branch push, PR,
merge, post-merge CI verification) is the remaining work before this
step can be marked fully COMPLETE — recorded honestly below, not
assumed.

## 1. Repository audit / baseline

- `git rev-parse HEAD` / `origin/main`: both `5e84c59891917ba9e0939394037b7e4071d7a128`,
  confirmed identical after `git fetch origin main`, matching the task
  instruction's stated known state.
- `git status`: clean before starting (two unrelated untracked scratch
  files, `my_rag.py` and `evaluation/_step30_framework_research_raw.md`,
  predating this task).
- **Baseline `pytest -q`: 549 passed, 13 deselected** — run before any
  change, not trusted from prior conversation summaries per the
  instruction's own explicit warning.
- Baseline `ruff check .`: clean except the one pre-existing hit on
  `my_rag.py` (unrelated personal scratch file, not part of this or any
  prior step's diff).
- Baseline `mypy src/ragtorch`: `Success: no issues found in 27 source
  files`.
- Inspected directly before designing anything: `src/ragtorch/`'s full
  tree (no `retrieval` package existed), `ragtorch/__init__.py`'s
  export style, `ragtorch/core/__init__.py` and
  `ragtorch/evaluation/__init__.py`'s subpackage-docstring +
  explicit-`__all__` convention (followed exactly for the new
  package), `tests/unit/<subpackage>/test_<module>.py` layout,
  `benchmarks/step<N>_<name>.py` naming, the existing AST-based
  provider-independence test pattern
  (`test_architecture_module_has_no_provider_dependencies` in
  `tests/unit/core/test_architecture.py`, and the hot-path
  `isinstance` scan in `test_component.py`) — reused rather than
  reinvented for `test_provider_independence.py`, `evaluation/step31-evaluation.md`
  (`CompositionGraph`'s fan-in gap, kept out of scope here per the
  task's own explicit instruction), `docs/architecture/requirements-matrix-v0.1.md`
  (next free row confirmed as A85 via direct `grep`, not assumed),
  `examples/rag_consumer/`'s real `Retriever`/`Chunk`/`RetrievalResult`/
  `VectorStore` types (read in full before designing `HybridRetriever`),
  the existing CI workflow's `rag-consumer-demo` job (confirmed it
  installs `ragmodel==0.5.0` from real PyPI, not local source — directly
  relevant to a real integration problem found later, see §6), README's
  existing retrieval+generation example (matched its style for the new
  hybrid example), `pyproject.toml`'s version (`0.5.0`) and
  `dependencies = []`.

## 2. Design

- **`ragtorch.retrieval` as a new top-level subpackage**, imported the
  same way `ragtorch.evaluation` already is (`from ragtorch.retrieval
  import BM25Index, RankedItem, rrf`) — not re-exported into
  `ragtorch.__all__`, since the instruction's own documented import
  path is the subpackage form, matching precedent.
- **`BM25Index`/`rrf` are plain Python, not `Module`** — per the
  instruction's explicit reasoning (deterministic algorithms need no
  execution identity/lifecycle/provider concept), and consistent with
  this project's own repeated discipline of not adding framework
  coupling without evidence (A76/A78/A79/A83/A84 all reached the same
  kind of conclusion for other candidate abstractions).
- **`RankedItem[T]`, not `Document`/`Chunk`/`RetrievalResult`** — a
  minimal, generic, frozen value object; consumer-specific types
  correctly stay out of core, matching every prior step's conclusion on
  this exact question (A78/A79's "no real RAG consumer" findings,
  re-confirmed rather than revisited here).
- **Inverted index, not a full per-query document scan** — `token ->
  {doc_id: term_frequency}` built once at construction; `search()`
  only scores documents appearing in the query-term postings.
- **Deterministic tie-breaking, explicit, not implicit**: BM25 sorts by
  `(-score, insertion_order)`; RRF sorts by `(-fused_score,
  first_seen_order_across_rankings)` — neither relies on `id`
  orderability, only hashability, matching the instruction's explicit
  requirement to support ids like `1`, `"two"`, `("three",)`.

## 3. What was implemented

- `src/ragtorch/retrieval/__init__.py`: package docstring (reasoning
  for not using `Module`), explicit `__all__ = ["BM25Index",
  "RankedItem", "default_tokenizer", "rrf"]`.
- `src/ragtorch/retrieval/bm25.py`: `default_tokenizer` (stdlib `re`
  only, case-folding, word-like token extraction), `RankedItem[T]`
  (frozen, generic, `item`+`score`), `BM25Index[T]` (constructor
  validates `k1 >= 0`, `0 <= b <= 1`; `search()` validates `top_k >=
  1`; standard BM25 formula exactly as specified in the task
  instruction, verified by hand-computation, see §4).
- `src/ragtorch/retrieval/fusion.py`: `rrf()` (validates `k > 0`,
  `top_k >= 1` when given; standard RRF formula, 1-based ranks;
  duplicate-in-one-ranking suppression; deterministic tie-break).
- `examples/rag_consumer/src/hybrid_retriever.py`: `build_lexical_index()`
  (builds a `BM25Index[str]` keyed by the same `chunk_id` already used
  everywhere in the demo) and `HybridRetriever(Module)` (fuses the
  existing dense `Retriever`'s ranking with the lexical ranking via
  `rrf()`, maps fused ids back to real `RetrievalResult` objects using
  the dense retriever's own results, falling back to chunk metadata
  lookup for BM25-only matches — never fabricating a source).

## 4. Test results

**27 new tests, all passing** (`tests/unit/retrieval/`: 12 BM25 + 9 RRF
+ 2 provider-independence + 1 hybrid + 2 public-API = 26; plus 6 in
`examples/rag_consumer/tests/test_hybrid_retriever.py`, gated by
`pytest.importorskip`).

Full local suite: **576 passed, 13 deselected** (549 baseline + 27
new) — confirmed via direct `pytest -q` run, not assumed from the
individual file counts.

Key correctness checks performed, not merely asserted:

- **RRF formula verified by hand computation** against the task
  instruction's own worked example (`ranking1 = [A,B,C]`, `ranking2 =
  [B,C,A]`, `k=60`) — computed `A = 1/61 + 1/63 ≈ 0.032266`, `B = 1/62
  + 1/61 ≈ 0.032522`, `C = 1/63 + 1/62 ≈ 0.032002` independently in a
  scratch interpreter session, confirmed `B > A > C`, then confirmed
  the implementation produces byte-identical ordering and
  `pytest.approx`-matching scores (`test_fusion_scores_match_hand_computed_values`).
- **BM25 human tests run directly** in an interpreter before writing
  formal tests: the "cat"/"cat chased the mouse" example (d1, d3
  returned, d2 excluded, both positive scores) and the "python
  programming" specificity example (d1 ranks before d2, d3 absent) —
  both matched expectations exactly on the first real run.
- **Duplicate-in-ranking handling verified**: `["A", "A", "B"]` — `A`'s
  score computed using only its rank-1 occurrence (`1/61`), not
  `1/61 + 1/63` from also counting the rank-3 occurrence — confirmed
  by direct score assertion, not just "doesn't crash."
- **Arbitrary non-orderable hashable ids** (`1`, `"two"`, `("three",)`)
  confirmed to work in both `BM25Index` and `rrf` — a real test, not
  merely typed as `Hashable` and assumed to work.

## 5. Benchmark results

`benchmarks/step32_bm25_rrf.py` — actual measured output (this run, no
threshold asserted):

```
operation                                   mean (ms)  median (ms)
BM25 build, n=100                               0.760        0.706
BM25 search, n=100                             0.2132       0.1373

BM25 build, n=1000                              7.569        7.336
BM25 search, n=1000                            1.2644       1.2012

BM25 build, n=10000                            74.796       74.739
BM25 search, n=10000                          14.4519      13.8864

RRF fusion (two rankings, varying length):

rrf, ranking length=10                         0.0086       0.0080
rrf, ranking length=100                        0.0787       0.0750
rrf, ranking length=1000                       0.9247       0.8689
```

**Honest scaling characterization (not marketing claims)**: `BM25Index.__init__`
tokenizes and indexes every document once — cost scales with total
token count across the corpus, confirmed by the roughly 10x-per-10x-
corpus-growth pattern in the numbers above (0.76ms → 7.6ms → 75ms for
100 → 1,000 → 10,000 documents, each synthetic document having a fixed
20-token length in this benchmark). `search()` only scores documents
appearing in the query-term postings, not a full corpus scan — its
growth is driven by how many documents share query terms, which in
this benchmark's synthetic corpus (a small fixed vocabulary reused
across all documents) means most documents match, so search time still
grows with corpus size; a real corpus with more vocabulary diversity
per document would show a smaller matching-document set and
correspondingly cheaper searches. `rrf()`'s cost is linear in total
items across all rankings, confirmed directly (0.009ms → 0.079ms →
0.92ms for ranking lengths 10 → 100 → 1,000, consistent with roughly
linear growth). **This is a dependency-free in-memory implementation
appropriate for small/local corpora and as a provider-independent
primitive. It is not claimed to be a distributed production search
backend** — stated in the benchmark's own printed output, not only in
this document.

## 6. Provider-independence result

`tests/unit/retrieval/test_provider_independence.py` — AST-based import
scan (reusing the established `test_architecture_module_has_no_provider_dependencies`
pattern from `tests/unit/core/test_architecture.py`, not reinvented),
checking both `bm25.py` and `fusion.py` against a forbidden list
(`openai`, `anthropic`, `google`, `cohere`, `pinecone`, `chromadb`,
`qdrant`, `weaviate`, `langchain`, `llama_index`, `haystack`,
`requests`, `httpx`, `urllib3`, `aiohttp`, `torch`, `transformers`).
**Both pass** — confirmed by direct `ast.parse()` walk over each
module's actual source (not a naive substring grep, which would
false-positive on `"torch"` inside `"ragtorch"`, exactly the false
positive this project's own established pattern already guards
against).

## 7. Dependency result

`pyproject.toml`'s `dependencies = []` **unchanged** — confirmed by
direct inspection before and after this step's changes; zero lines
touched in the `[project]` section. The only new imports in
`bm25.py`/`fusion.py` are stdlib (`math`, `re`, `collections`,
`dataclasses`, `typing`) — confirmed by the same AST scan in §6.

## 8. Hybrid consumer result

`examples/rag_consumer/src/hybrid_retriever.py`'s `HybridRetriever`
genuinely performs dense + lexical hybrid retrieval using the real
consumer's existing types, confirmed by direct execution (not merely
unit-tested in isolation):

```
$ python hybrid_smoke.py   # dense=HashingEmbedder, lexical=BM25Index
c1 Cats 0.0325
c3 Fish 0.0164
c2 Dogs 0.0159
```

**A real, non-hypothetical bug was found and fixed during this
integration's own testing** — recorded honestly, not glossed over: an
early version of `HybridRetriever.forward()` preserved the *original*
dense-only `RetrievalResult.score` on results that also appeared in the
dense ranking, instead of replacing it with the fused RRF score. This
silently misrepresented ranking confidence — a chunk ranked first by
the actual fusion could display a lower `.score` than a chunk ranked
third, because it was still showing leftover dense-only numbers. Caught
by directly comparing `HybridRetriever`'s output against a standalone
`rrf()` call on the same `dense_ids`/`lexical_ids` inputs and noticing
the scores didn't match (`test_hybrid_retriever_result_scores_match_direct_rrf_call`
is the resulting regression test). Fixed by constructing a new
`RetrievalResult` with the fused score, preserving only the
dense-sourced metadata (`text`/`url`/`title`/`document_id`) rather than
the whole original object.

**A second real, environment-level problem was found and fixed**: the
demo's `rag-consumer-demo` CI job installs `ragmodel==0.5.0` from real
PyPI (confirmed by reading `.github/workflows/ci.yml` directly), which
predates this step's addition of `ragtorch.retrieval` and does not have
it. Reproduced the exact failure mode locally by installing
`ragmodel==0.5.0` (no local source) into a fresh venv and running the
demo's test suite: a **collection-time `ModuleNotFoundError`** that
aborts the entire test run, not merely one failing test. Fixed with
`pytest.importorskip("ragtorch.retrieval")` at the top of
`test_hybrid_retriever.py`, re-verified against both the exact
CI-reproducing environment (86 passed, 1 skipped — no collection
failure) and the local dev environment with the new package installed
(92 passed, all real). This is the correct fix given the constraint
that the CI job's whole purpose is testing the *published* package —
changing its install source to local source was considered and
rejected as defeating that job's purpose.

## 9. Limitations

- `BM25Index` has no mutation/incremental-indexing methods — documents
  are fixed at construction. Deliberately not designed further without
  a real consumer need, per the task instruction's own explicit
  scoping.
- `BM25Index` is not a distributed/persistent search backend — stated
  plainly, not implied to be otherwise.
- `HybridRetriever`'s tests do not run in the demo's CI job until a
  future PyPI release actually publishes `ragtorch.retrieval` — this is
  a real, temporary gap, not silently hidden; `pytest.importorskip`
  means the tests will start running automatically the moment that
  release happens, with no further code change needed.
- `HybridRetriever` was **not** wired into the demo's default
  `build_pipeline()`/Colab notebook — it exists and is tested as an
  available alternative retrieval path, not the default. No evidence
  was gathered in this step about whether the default should change,
  and changing a default without that evidence would repeat exactly
  the kind of premature decision this project has consistently avoided.
- `default_tokenizer`'s word-like token extraction (`\w+`, case-folded)
  is intentionally minimal — no stemming, no language-specific rules,
  no domain-specific normalization; callers needing those supply their
  own `tokenizer` callable, exactly as the public contract specifies.

## 10. Decision

- **Does BM25 provide a useful provider-independent primitive?** Yes —
  demonstrated via 12 passing unit tests covering real relevance
  behavior (not just "doesn't crash"), zero dependencies, and a
  provider-independence scan confirming no vendor coupling.
- **Does RRF work correctly and deterministically?** Yes — verified
  against a hand-computed worked example matching the task
  instruction's own numbers exactly, with documented and tested
  duplicate-handling and tie-breaking.
- **Can the real consumer perform dense + lexical hybrid retrieval?**
  Yes — demonstrated with real execution against the existing
  `Retriever`/`Chunk`/`RetrievalResult`/`VectorStore` types, unmodified,
  including catching and fixing a real bug during that integration.
- **Did we need `CompositionGraph` fan-in?** No — `HybridRetriever` is
  a single `Module` internally calling the dense retriever and BM25
  index sequentially within its own `forward()`, not a graph-level
  fan-in composition. `CompositionGraph`'s fan-in ≤ 1 limitation (Step
  31/A84) remains untouched and unneeded for this integration.
- **Did we need `ExecutionEngine` changes?** No — `HybridRetriever` is
  a drop-in replacement for the existing `Retriever` at exactly the
  same pipeline integration point; `pipeline.py`'s `RetrieveStage`/
  `Sequential` composition is unchanged (confirmed via `git diff
  --stat` showing zero lines touched in `pipeline.py`).
- **Did runtime dependencies remain zero?** Yes — confirmed directly,
  `dependencies = []` unchanged.
- **What remains intentionally out of scope?** Incremental/mutable
  BM25 indexing; wiring `HybridRetriever` as the demo's default
  retrieval path; publishing this to PyPI (per the task's own explicit
  instruction not to bump the version in this step); any change to
  `CompositionGraph`, `ExecutionEngine`, `ExecutionContext`, `Trace`,
  `Run`, `Module.__call__`, async execution, or provider adapters — all
  explicitly untouched, confirmed via `git diff --stat` on those exact
  files/directories.

This step does **not** claim universal production superiority for
BM25/RRF as implemented — only that they are correct, tested,
dependency-free, and genuinely useful to the one real consumer this
project has (`examples/rag_consumer/`), for the corpus sizes that
consumer's own architecture already targets.

## Git / CI closure

(Filled in after real GitHub-facing work — branch push, PR, CI
verification, merge, post-merge CI — following this project's standing
rule that PR CI and post-merge CI must both be independently verified
via the actual GitHub Actions API, never assumed from local test
success alone.)
