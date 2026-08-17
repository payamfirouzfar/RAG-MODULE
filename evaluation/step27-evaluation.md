# Step 27 Evaluation — First Real RAG Consumer / Provider-Boundary Discovery

## Status

**Step 27: COMPLETE. Outcome A — no new production abstraction justified; the
deterministic discovery pipeline built in this step is itself still a synthetic
consumer, not a real one, so the bar Step 26 set ("no provider abstraction without a
real RAG consumer") is not yet met.** The experiment substantially strengthens the
evidence base for whenever a real consumer does appear, and is preserved for that
purpose, but nothing in `src/ragtorch/` changed.

This distinction matters and is stated precisely, per this project's evidence-vocabulary
discipline: this step ran a **real, working, adversarially-tested pipeline** — that is
genuine, reproducible evidence, not a guess. But the pipeline's *consumer* — the corpus,
the queries, the embedder, the generator — is still entirely synthetic and
deterministic, constructed specifically to generate evidence, not an actual application
built by an actual user with actual needs. Step 26 and this step's own Phase 2
instructions both call this experiment a "toy" pipeline / "discovery fakes" — never a
real consumer. Treating a self-constructed toy as satisfying "we now have that
justification from actual package usage" would misrepresent the evidence.

## Evidence vocabulary used in this document

- **Ran / Measured**: actually executed and observed, with output captured.
- **Discovered coupling**: a concrete dependency between two pipeline stages found by
  deliberately trying to break it (Phase 4/6), not assumed from design intuition.
- **Real consumer**: an actual, non-synthetic application using the package for its own
  purpose — still does not exist after this step.

---

## 27A — Repository audit

Verified directly, not trusted from prior summaries:

- `git status`: clean. `git rev-parse HEAD`: `8406c264475a4952438ca98840d6fa0029c34cde`,
  confirmed identical to `origin/main` after `git fetch origin main`.
- `git log -5 --oneline` confirms Step 26's two commits (`260ce7c`, `8406c26`) and its
  merge commit (`2d849d0`) are present and are the most recent history.
- `src/ragtorch/core/component.py` (`Component` Protocol, `@runtime_checkable`,
  `name`/`component_type`/`__call__`) and `src/ragtorch/core/ports.py`
  (`InputPort`/`OutputPort`/`is_compatible`/`check_connection`) were read in full —
  confirmed both are structural, immutable, provider-agnostic, and already exactly the
  shape this step's Protocol-based fakes (`Chunker`, `Embedder`, `VectorStore`,
  `Retriever`, `PromptBuilder`, `Generator` in `rag_fakes.py`) turned out to need —
  independently arrived at, then confirmed consistent with the existing precedent.
- `src/ragtorch/core/logging.py` read in full: confirmed the existing redaction policy
  (`redact()`, `is_sensitive_key()`, `_SENSITIVE_KEY_MARKERS`) already covers exactly the
  "never log raw prompts, documents, retrieved content, or secrets" rule this step's
  security tests needed to verify against — no new logging mechanism was required.
- `src/ragtorch/core/module.py` read (imports, `Module.__init__`/`forward`/`__call__`
  shape) to confirm how the discovery fakes could be wrapped in `Module`/`Sequential`
  for the compatibility test (27I).
- Step 26's evaluation (`evaluation/step26-evaluation.md`) and requirements matrix rows
  A76/A78 re-read in full — both explicitly concluded zero real RAG consumer exists and
  that no provider boundary should be designed without one. This step's job was to
  attempt to produce that real consumer, or determine why one still doesn't exist.

## 27B — Real consumer definition

Built `tests/discovery/rag_fakes.py`: a complete, provider-independent, deterministic
toy RAG shape (documents → chunking → embedding → indexing → retrieval → context
assembly → generation), using a 3-document corpus and entirely local, swappable Python
test doubles (`FakeChunker`/`HashingEmbedder`/`CountingEmbedder`/`InMemoryVectorStore`/
`InvertedIndexVectorStore`/`SimpleRetriever`/`KeywordRetriever`/`SimplePromptBuilder`/
`EchoGenerator`/`WordCountGenerator`/`FailingEmbedder`/`FailingGenerator`). No network,
no API key, no external model, no vector database, no third-party AI dependency anywhere
in this file or its tests — confirmed by `test_no_provider_import_leaks_into_ragtorch_core`,
which asserts `pyproject.toml`'s `dependencies == []` remains true.

These fakes are explicitly **not** exported from `ragtorch`'s public API (Phase 11 rule)
— they live under `tests/discovery/`, are excluded from `mypy`'s `files = ["src/ragtorch"]`
scope, and are collected by the default `pytest` run (no `packaging`-style marker needed,
since they run in milliseconds with zero external state).

## 27C — Data contract inventory

Seven candidate types were built and exercised (`Document`, `Chunk`, `Embedding`,
`ScoredChunk`, `RetrievalResult`, `GenerationResult`) — `PromptTemplate` was **not**
built as a type; a prompt turned out to just be a `str`, produced by a
`PromptBuilder` Protocol's `__call__`, with no evidence any structured representation
was needed beyond that.

For each type built:

| Type | Necessary? | Fields (all load-bearing, none speculative) | Immutable? | Identity | Serializable shape |
|---|---|---|---|---|---|
| `Document` | Yes — every stage needs a source unit | `id`, `text`, `metadata: dict` | Yes (frozen dataclass) — proven safe by `test_document_chunk_embedding_types_are_immutable` | `id: str`, deliberately independent of content equality | `dict`/`str`/open-ended metadata — all JSON-shaped already |
| `Chunk` | Yes — retrieval operates on chunks, not whole documents | `id`, `document_id`, `text`, `metadata` | Yes | `id: str`; `document_id` preserves traceability without embedding the full `Document` | Same as `Document` |
| `Embedding` | Yes — needed to pair a vector with the chunk it represents | `chunk_id`, `vector: tuple[float, ...]` | Yes | keyed by `chunk_id`, not its own id — no evidence a separate embedding identity is needed | Trivially serializable; deliberately not tied to `numpy`/any specific array type |
| `ScoredChunk` | Yes — retrieval output needs both the chunk and why it was picked | `chunk`, `score: float` | Yes | N/A (a scoring pair, not an entity) | Trivial |
| `RetrievalResult` | Yes — the query and its ranked chunks need to travel together to the prompt-builder and generator stages | `query`, `scored_chunks: tuple[ScoredChunk, ...]` | Yes (tuple, not list — rank order is meaningful output) | N/A | Trivial |
| `GenerationResult` | Yes — the final output needs both text and citation-capable source tracking | `text`, `source_chunk_ids: tuple[str, ...]` | Yes | N/A | Trivial |
| `PromptTemplate` | **No** — a `str` sufficed in every test; no case in Phase 4/6 required structure beyond plain text | — | — | — | — |

**Sensitive fields**: `Document.metadata`/`Chunk.metadata` are the only fields that could
carry secrets (e.g. an accidentally-embedded API key in provenance metadata) — verified
directly via `test_metadata_containing_a_secret_like_key_is_not_logged_by_default`, which
routes metadata through the existing `is_sensitive_key()`/`redact()` functions before
logging and confirms the raw value never appears in `caplog.text`.

**Metadata design decision recorded, not implemented**: an open `dict[str, object]` was
used rather than a typed metadata schema. This was **not decided as a permanent choice**
— it was the minimum needed to make the fakes work, and a real consumer may reveal a need
for typed metadata (e.g. required provenance fields) that this experiment cannot surface,
since its own corpus was hand-authored specifically to avoid needing one.

## 27D — Provider-boundary experiment (discovered couplings)

Ran, not assumed:

1. **Embedder dimensionality is NOT a pipeline-wide constant.** `HashingEmbedder`
   (16-dim, word-hashing) and `CountingEmbedder` (8-dim, character-trigram) are
   algorithmically and dimensionally unrelated, and both ran the complete pipeline to
   completion with zero code change beyond swapping which instance was passed in
   (`test_embedder_can_be_replaced_with_a_different_dimensionality`). **No abstraction
   anywhere assumes a fixed embedding dimensionality.**
2. **Generator is fully independent of Embedder.** `EchoGenerator` (concatenates
   retrieved text) and `WordCountGenerator` (reports word counts — a completely
   different output shape) both ran successfully regardless of which embedder produced
   the retrieval (`test_generator_can_be_replaced_independently_of_embedder`). **No
   coupling found between generation strategy and embedding strategy.**
3. **Discovered real, unavoidable coupling**: a query embedding and a store's stored
   embeddings *must* come from the same embedder (same dimensionality/semantics) or
   retrieval fails. This is not a design flaw — it is an intrinsic property of
   vector similarity search, confirmed by `test_a_query_and_corpus_embedded_with_different_embedders_cannot_be_mixed`,
   which shows `InMemoryVectorStore.search()` raises `ValueError` loudly on a
   dimensionality mismatch rather than silently returning garbage-ranked results. **This
   is evidence in favor of, not against, keeping Embedder/VectorStore pairing an explicit
   application-level responsibility** rather than something core should try to enforce or
   abstract away.
4. **Store does not have to be vector-based at all.** `InvertedIndexVectorStore` (a
   plain keyword inverted index, ignoring embeddings entirely) plus `KeywordRetriever`
   produced a working retrieval result with zero vector math
   (`test_vector_store_can_be_replaced_with_a_non_vector_backed_store`). This is
   significant: it proves a `Retriever` contract does not need to assume "retrieval
   implies embeddings" — a real future `Retriever` Protocol must not bake in an
   `Embedder`/`VectorStore` dependency as part of its own shape.
5. **Discovered contract weakness (not fixed, recorded)**: `VectorStore.search(self,
   query_vector, top_k)`'s signature itself already assumes vector-based retrieval —
   `InvertedIndexVectorStore.search()` had to raise `NotImplementedError` and expose a
   separate `search_by_keywords()` method instead, because the Protocol's own parameter
   shape (`query_vector: tuple[float, ...]`) cannot represent a keyword query. **This is
   real evidence that "VectorStore" and "Retriever" should not be conflated as one
   contract** — a finding directly useful to Phase 5's architecture options, and recorded
   here rather than silently worked around.

## 27E — Architectural options comparison

Because Outcome A was reached (27N), this comparison is preserved as evidence, not as a
committed design — matching Step 26's same discipline of recording design-space work
without committing to it prematurely.

| Option | Provider independence | Model independence | Storage independence | Optional deps | Package size | Install simplicity | API stability | Serialization | Async future | Multimodal future | GraphRAG future | Observability | Testing | Evaluation | Security | Backcompat | Composability | Replaceability | Discoverability | Doc burden | Maintenance burden |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A. RAG abstractions in `ragtorch.core` | Weak — risks core importing provider-shaped types | Weak, same reason | Weak, same reason | N/A — core has no extras today | Grows core's own footprint | Simple (nothing new to install) | Risky — core's API is this project's most stability-guarded surface (A16/ADR-010) | Undesigned either way | Forces new async surface onto the most hot-path-protected code in the repo | Orthogonal | Orthogonal | Free (existing `Trace`/`EventBus` already provider-agnostic) | Easy | Easy | Same redaction rules apply everywhere regardless | High risk — a wrong choice here is hardest to walk back | Reuses `Module`, but couples RAG shape to Module's own evolution | Reuses `Module` pattern already proven by the discovery fakes | High — same package as everything else | Low, until it grows | Concentrates all future maintenance in the single most-tested module |
| B. `ragtorch.rag` — provider-independent contracts only | Strong | Strong | Strong | No new extra needed for pure data contracts | Small, additive | Simple | A narrow new surface, easier to keep stable than growing core | Same undesigned status, but isolated | Isolated from `Module`'s hot path — free to design separately | Isolated, easier to extend without touching core | Isolated, same reason | Free if types eventually flow through `Module`/`Component` | Easy — this step's own fakes prove the pattern works | Easy | Same | Low risk — a new, small package can evolve faster than core | Composes via `Component`, proven in 27I | Proven — every fake swapped cleanly | Medium — a new import path to document | Small, scoped to a handful of frozen dataclasses | Low — no execution logic, only data shapes |
| C. `ragtorch.adapters` — provider integrations | Strong by construction | Strong | Strong | Would require actual provider extras — none exist yet, evidence doesn't support this yet | Would add real weight (SDKs) if implemented now | Would break the zero-dependency clean install Step 25/A77 proved | Adapters can evolve independently of core | Depends on provider SDK's own serialization | Depends on provider SDK | Depends | Depends | Depends on adapter design | Requires mocking real SDKs — harder than this step's plain fakes | Hard without real providers | Highest risk surface (real credentials, real network calls) | Provider SDK version churn is now this project's problem too | N/A yet | N/A yet | High, once it exists | High — provider docs change constantly | Highest — real external dependencies to track |
| D. Split: `core` / `rag` / `adapters` | Strong | Strong | Strong | Clean separation, matches R11's target shape | Core stays exactly as light as today | Simple for users who only want `core` | Each layer's stability is scoped to its own concerns | Isolated to `rag` layer's contracts | Isolated | Isolated | Isolated | Free | Easy | Easy | Cleanest risk separation | Lowest overall risk — layers can each evolve at their own pace | Proven pattern (27I) | Proven | Requires the clearest documentation of the three real options | Medium — three things to document instead of one | Distributed, but each piece stays small |
| E. RAG entirely external, only `Component` | Strongest — literally zero ragtorch-side commitment | Strongest | Strongest | N/A | Zero growth | Simplest | Perfectly stable — nothing new ships | N/A | N/A | N/A | N/A | Works today (already proven — `Component` protocol satisfies this) | Trivial | Trivial | Trivial — nothing to secure | Zero risk | Already proven — this step's fakes ARE this option | Fully external | Lowest — nothing to discover, it's just "write your own" | Zero | Zero for ragtorch; all cost pushed to every downstream user re-deriving the same shapes this step already found |
| F. Hybrid: small `rag` data contracts + adapters + core kernel | Strong | Strong | Strong | Matches R11's eventual target | Core stays light, `rag` stays small, `adapters` stays optional | Simple base install, optional extras for real usage | Narrow contracts stay stable, adapters absorb churn | Best-positioned — contracts isolated from adapter churn | Best-positioned | Best-positioned | Best-positioned | Free | Easiest — reuses this step's own proven fake pattern | Easiest | Cleanest | Lowest long-term risk | Proven | Proven | Best of B/C/D combined, once justified | Medium | Best-distributed of all options |

**Observation, not decision**: Options B, D, and F consistently score best — this is the
same conclusion Step 26's Phase 4 comparison reached, now reinforced with concrete
28-test-case evidence rather than only design reasoning. Option E is what this step's
discovery experiment itself already **is** — it is not a hypothetical, it is exactly
what was built and it worked without friction. This is meaningful: it demonstrates the
"do nothing new" option is not merely acceptable but genuinely functional today.

## 27F — Adversarial review

All 20 required adversarial cases were run as actual tests (`tests/discovery/
test_rag_consumer.py`), not merely reasoned about:

1. Different embedding dimensions — **ran**, passed (27D #1)
2. Different embedding implementations — **ran**, passed (27D #1)
3. Different retrieval algorithms (vector vs. keyword) — **ran**, passed (27D #4)
4. Different stores (in-memory vector vs. inverted index) — **ran**, passed (27D #4)
5. Empty corpus — **ran** (`test_empty_corpus_produces_empty_retrieval_not_a_crash`):
   produces an empty `RetrievalResult`, not a crash; `GenerationResult` still produced
   with `source_chunk_ids == ()`
6. Empty query — **ran** (`test_empty_query_does_not_crash_the_pipeline`): pipeline
   completes
7. No retrieval results — same as #5
8. Duplicate documents — **ran** (`test_duplicate_documents_do_not_break_retrieval`):
   pipeline completes, no crash
9. Duplicate chunk IDs — **ran** and a real, unresolved risk was found:
   `test_duplicate_chunk_ids_across_documents_do_not_silently_collide` demonstrates that
   two `Document`s sharing the same `id` (a real ingestion bug, not this fake's own
   behavior — the fake never produces colliding IDs itself) would silently overwrite
   each other in `InMemoryVectorStore._chunks_by_id`. **Recorded as an open risk (27O),
   not fixed** — fixing it responsibly requires a real `Document` identity contract,
   which 27C explicitly declined to freeze without a real (non-fake) ingestion consumer.
10. Missing metadata — **ran**, defaults to `{}`, never `None`
    (`test_missing_metadata_defaults_to_empty_dict_not_none`)
11. Provider failure (embedding) — **ran**
    (`test_embedding_provider_failure_propagates_not_silently_swallowed`): `RuntimeError`
    propagates unmodified, not swallowed or wrapped
12. Generator failure — **ran**
    (`test_generation_provider_failure_propagates_not_silently_swallowed`): same
13. Embedding failure — same as #11
14. Store failure — implicitly covered by the dimensionality-mismatch `ValueError` (27D
    #3), which is itself a store-level failure mode
15. Retrieval failure — covered by #11/#13 (retrieval depends on embedding)
16. Very large metadata — **ran**
    (`test_large_metadata_is_preserved_without_truncation`): a 100,000-character value
    survives untruncated
17. Unicode — **ran** (`test_unicode_text_survives_the_full_pipeline`): accented Latin,
    CJK, emoji, and Arabic script all survive the complete pipeline
18. Binary/multimodal payload possibility — **not implemented**, but explicitly examined:
    `Document.text: str` would need a new field or a different type entirely to carry
    binary/image payloads; nothing in the current fake shape blocks adding one later
    (dataclasses are extensible), but nothing here proves what that field should look
    like either — correctly left to Phase 6/multimodal's own future audit (Step 26
    already deferred this)
19. Async provider possibility — **not implemented**, examined: every Protocol here
    (`Chunker`, `Embedder`, etc.) is defined with a plain `__call__`, not `async def` —
    swapping to `async def __call__` would be a breaking change to these specific
    Protocols, but since none of them are public ragtorch API (27, Phase 11 rule), that
    cost is zero today. A real future contract would need to decide this upfront rather
    than retrofit it.
20. Serialization/deserialization possibility — **not implemented**, examined: every
    frozen dataclass here (`Document`, `Chunk`, `Embedding`, etc.) uses only
    JSON-representable field types (`str`, `dict[str, object]`, `tuple[float, ...]`) —
    no evidence of a serialization blocker, but no serialization was actually
    implemented or tested, so this remains an open question, not a proven capability.

**Does the proposed contract shape accidentally assume text-only RAG?** Partially yes:
`Document.text: str` is a hard assumption. This was surfaced directly by adversarial case
#18 and is recorded as a known, real limitation of this experiment's contract shape —
not something this step chose to fix, since fixing it without a real multimodal consumer
would be exactly the premature design Step 26 (Phase 6) already declined to do.

**Vision RAG / multimodal RAG / GraphRAG / SQL RAG / hybrid retrieval / agentic RAG** —
none implemented, per instruction. Findings: hybrid retrieval (vector + keyword) is
already demonstrated as compatible with the `Retriever` Protocol shape (27D #4), since
`KeywordRetriever` needed no special-casing. GraphRAG, SQL RAG, and agentic RAG remain
entirely unexamined by this experiment — no fake was built for any of them, and nothing
here should be read as evidence about their fit.

## 27G — Security review

- Confirmed the existing project-wide rule ("raw prompts, documents, retrieved content,
  and secrets must not be logged by default," `core/logging.py`) already fully covers
  this experiment's needs — no new logging mechanism was designed or is needed.
- `test_metadata_containing_a_secret_like_key_is_not_logged_by_default`: a
  `Document.metadata` value resembling an API key, routed through `is_sensitive_key()` +
  `redact()` before logging, never appears in captured log output.
- `test_raw_document_text_is_not_logged_by_default`: raw document text routed through
  `redact()` never appears in captured log output.
- Not tested (no implementation exists to test): prompt injection, malicious provider
  payloads, provider exceptions containing credentials, serialization leakage — all
  remain open risks for whenever a real provider adapter is designed (consistent with
  Step 26's Phase 9 risk table, which already assigned these to "adapters" or
  "application layer," not core).

## 27H — Performance benchmark

`benchmarks/step27_rag_discovery_pipeline.py` measures each stage of the discovery
pipeline separately (200 iterations per stage, 50 for the full pipeline), against a
50-document synthetic corpus. Actual measured output (this run):

```
chunking (50 docs)                       mean=   0.0668ms  median=   0.0809ms
embedding (50 chunks, 16-dim)            mean=   0.2778ms  median=   0.1765ms
indexing (50 chunks into store)          mean=   0.0023ms  median=   0.0022ms
retrieval (50-chunk store, top_k=5)      mean=   0.3182ms  median=   0.3112ms
prompt construction                      mean=   0.0006ms  median=   0.0006ms
generation (fake, no real model)         mean=   0.0014ms  median=   0.0012ms
complete pipeline (50 docs, cold index)  mean=   0.6327ms  median=   0.5296ms
```

No threshold is asserted, matching this project's established benchmark discipline
(Step 18, Step 23). **This measures only the discovery fakes' own overhead** — real
embedding/LLM provider network latency will overwhelmingly dominate all of these numbers
once real providers exist, so none of this should be read as evidence about real-world
RAG performance, only as confirmation that the *shape* of the pipeline introduces no
surprising overhead of its own.

## 27I — Tests

`tests/discovery/test_rag_consumer.py`: 21 discovery/characterization tests (explicitly
not public-API contract tests — see Phase 11 rule), covering:

- Complete deterministic pipeline execution + determinism across repeated runs (2 tests)
- Provider-replacement experiment: embedder swap, generator swap, dimensionality
  mismatch, non-vector store swap (4 tests)
- Adversarial edge cases: empty corpus, empty query, duplicate documents, duplicate
  chunk IDs, missing/large metadata, Unicode, embedding/generation failure propagation
  (9 tests)
- Data contract properties: citation/source-id preservation, immutability (2 tests)
- Security: secret-in-metadata redaction, raw-document-text redaction (2 tests)
- Compatibility: fakes compose through real `Module`/`Sequential` execution, no
  provider dependency leaks into `ragtorch`'s own `pyproject.toml` (2 tests)

All 21 pass. Full suite: **549 passed, 11 deselected** (528 pre-existing + 21 new).

## 27J — Compatibility review

Zero changes to `src/ragtorch/**` — confirmed via `git diff --stat`. Public API,
existing contracts, and all 528 pre-existing tests are unaffected. The new discovery
tests/fakes/benchmark live entirely under `tests/discovery/` and `benchmarks/`, neither
of which is part of the installed wheel (confirmed by Step 25's own wheel-content tests,
`tests/packaging/test_clean_install.py::test_wheel_contains_only_intended_runtime_files`,
which already asserts `tests/` is never packaged).

## 27K — Dependency review

No new runtime or dev dependency was added. `pyproject.toml`'s `dependencies = []`
remains unchanged — verified directly by
`test_no_provider_import_leaks_into_ragtorch_core`, which reads `pyproject.toml` via
`tomllib` and asserts the runtime dependency list is still empty.

## 27L — CI

- Branch: `audit/step27-real-rag-consumer`
- PR: [#34](https://github.com/payamfirouzfar/RAG-MODULE/pull/34)
- First PR CI run [32077963630](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32077963630)
  at commit `0110566` **failed**: `test (3.12)` hit
  `ModuleNotFoundError: No module named 'tests'` — `test_rag_consumer.py` used an
  absolute `from tests.discovery.rag_fakes import ...` package import, which only
  resolved locally because this dev environment's editable install happened to expose
  the repo root on `sys.path`; CI's fresh install does not guarantee that for a bare
  `tests` directory with no top-level `tests/__init__.py`. Fixed by switching to a
  relative import (`from .rag_fakes import ...`) and consolidating four scattered local
  `Embedding` imports into the top-level import list. Verified by reproducing the exact
  CI install path in a genuinely fresh venv (`python -m venv` + fresh
  `pip install -e ".[dev]"`, not the pre-existing dev venv) before pushing again.
- Second PR CI run [32079291312](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32079291312)
  at commit `c724789` **failed again, differently**: `test (3.10)` hit
  `ModuleNotFoundError: No module named 'tomllib'` in
  `test_no_provider_import_leaks_into_ragtorch_core` — the exact same `tomllib`-is-
  3.11+-only gap already discovered and fixed in Step 25 (A77), reproduced here because
  the same fallback pattern was not applied to this new test. Fixed identically (`try:
  import tomllib / except ModuleNotFoundError: import tomli as tomllib`), verified
  directly against a real Python 3.10 interpreter
  (`py -3.10 -m pytest tests/discovery/test_rag_consumer.py::test_no_provider_import_leaks_into_ragtorch_core`
  — 1 passed) before pushing again. `tomli` was already a conditional dev dependency
  from Step 25, so no `pyproject.toml` change was needed this time.
- Third PR CI run [32079460864](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32079460864)
  at commit `fdfc3d8` (final PR head) — **all 6 jobs succeeded**: `test` × {3.10, 3.11,
  3.12} and `packaging` × {3.10, 3.11, 3.12}.
- PR diff scope verified via `gh pr view --json files` immediately before merge: exactly
  the six files listed in 27M, no `src/ragtorch/**` changes.
- Merged via `gh pr merge 34 --merge`. Merge SHA verified directly via
  `gh pr view --json mergeCommit`: **`853f30b5cccfcd371a5032e25cf05ac4f7f9f904`**.
- Post-merge CI run [32079550874](https://github.com/payamfirouzfar/RAG-MODULE/actions/runs/32079550874)
  on `main`, head SHA confirmed as the exact merge commit `853f30b` — **all 6 jobs
  succeeded**:
  - `test (3.10)`, `test (3.11)`, `test (3.12)`: **549 passed, 11 deselected** each.
  - `packaging (3.10)`, `packaging (3.11)`, `packaging (3.12)`: **11 passed** each.
- Local branch fast-forwarded to `853f30b` (`git checkout main && git pull`), confirmed
  via `git log --oneline -3`.

## 27M — Diff review

`git status --short` before commit shows exactly:
- `benchmarks/step27_rag_discovery_pipeline.py` (new)
- `tests/discovery/` (new directory: `__init__.py`, `rag_fakes.py`, `test_rag_consumer.py`)
- `evaluation/step27-evaluation.md` (new, this file)
- `docs/architecture/requirements-matrix-v0.1.md` (one new appended row, A79)

No changes to any file under `src/ragtorch/`. No secrets (the one "sk-"-prefixed string
in the test suite is an intentional fake-secret marker used to verify redaction, not a
real credential — confirmed by direct inspection). No `.claude` artifacts (already
excluded by `.gitignore` since Step 25/A77). No provider dependency added
(`pyproject.toml`'s `dependencies` list is untouched). No accidental public exports —
`src/ragtorch/__init__.py`'s `__all__` is untouched. No historical ADR wording changed.

## 27N — Architectural decision

**Outcome A: no new production abstraction is justified yet.**

This is a closer call than Step 26's Outcome A, and the reasoning must be precise:

- This step's experiment is genuinely useful evidence — it is a real, working,
  adversarially-tested pipeline that discovered concrete couplings (27D) a purely
  theoretical design review could not have found (e.g., the `VectorStore.search()`
  signature's hidden vector-only assumption, finding #5).
- But the instruction's own gate is explicit: "We now have that justification from
  actual package usage" was the premise handed to this step, and this step's job was to
  validate or challenge that premise with real evidence. The honest finding is that the
  premise is **not yet true** — this experiment's "consumer" is a corpus and set of
  fakes deliberately built by this step itself to generate evidence, not an actual
  application built by an actual user solving an actual problem. Every one of the 21
  tests exists to characterize behavior, not to satisfy a real requirement someone
  brought to this project.
- Choosing Outcome B/C/D now, on the strength of a self-constructed toy, would repeat
  exactly the anti-pattern this project's own history (A11, A61, A76, A78) has
  consistently and explicitly rejected: designing infrastructure ahead of genuine
  demand, dressed up as "evidence-based" because a benchmark and adversarial tests
  exist. A rigorous toy is still a toy.
- The architecture comparison (27E) and data-contract inventory (27C) are preserved in
  full, specifically so that if/when a real consumer appears — someone actually building
  a RAG application with this framework, not this step's own synthetic exercise — that
  future step does not have to re-derive this evidence. This step is a meaningfully
  stronger version of Step 26's groundwork, not a repeat of it: it now includes running
  code, discovered couplings, and adversarial-case results, not just prose comparison.
- **No ADR is created.** ADR-005 remains the sole governing decision. Creating an ADR to
  formalize a boundary this step itself concludes is not yet justified would be
  self-contradictory.

## 27O — Final conclusion

The discovery pipeline built in this step is real, working, and adversarially tested —
but it is still a synthetic consumer this step constructed for the purpose of generating
evidence, not a real RAG application built by an actual user. Per the explicit standard
this step itself was asked to validate ("no provider abstraction without a real RAG
consumer"), that standard remains unmet. No production code changed. The provider-
boundary design comparison, data-contract inventory, discovered couplings, and
adversarial-case results are all preserved as the strongest evidence base this project
has produced so far, ready for whenever a genuine external consumer appears.

**Open risks carried forward:**
- Duplicate `Document.id` values across ingested documents would silently overwrite
  prior chunks in a naive store implementation (27F #9) — unresolved, requires a real
  `Document` identity contract to fix responsibly.
- `Document.text: str` hard-codes a text-only assumption (27F, adversarial finding) —
  unresolved, deferred to a future multimodal audit with real evidence.
- Async and serialization support for any future contract remain fully undesigned (27F
  #19, #20) — no blocker was found, but nothing was proven either.
- `VectorStore` and `Retriever` should likely not be the same contract (27D #5) — a
  concrete, evidence-backed design note for whenever Option B/D/F (27E) is eventually
  pursued.

R1/R2/R3/R6/R11 and A3/A6/A7/A8/A11 all remain fully open and Deferred, re-confirmed
rather than resolved — this is the third consecutive step (after A76, A78) to reach that
conclusion, now with the strongest evidentiary basis yet.
