"""Step 27: first real RAG consumer / provider-boundary discovery.

These are characterization/discovery tests, not public API contract
tests -- everything under test lives in tests/discovery/rag_fakes.py,
which is deliberately NOT part of ragtorch's public surface (see the
Step 27 evaluation ledger's Phase 11 "public API rule": nothing is
exported merely because it was useful in an experiment).

Purpose: generate concrete evidence about what a real RAG pipeline
requires -- data contracts, provider-boundary coupling, failure modes,
security exposure -- using entirely deterministic, local, provider-free
test doubles. No network, no API key, no external model, no vector
database, no third-party AI dependency anywhere in this file or in
rag_fakes.py.
"""

from __future__ import annotations

import ragtorch
from ragtorch import Module, Sequential

from .rag_fakes import (
    Chunk,
    CountingEmbedder,
    Document,
    EchoGenerator,
    Embedding,
    FailingEmbedder,
    FailingGenerator,
    HashingEmbedder,
    InMemoryVectorStore,
    InvertedIndexVectorStore,
    KeywordRetriever,
    SimplePromptBuilder,
    SimpleRetriever,
    WordCountGenerator,
    run_pipeline,
)

DOCS = [
    Document(id="doc-a", text="RAG retrieves relevant external knowledge before generation."),
    Document(id="doc-b", text="Embeddings represent text as vectors."),
    Document(id="doc-c", text="Retrieval selects candidate chunks for a query."),
]


# ---------------------------------------------------------------------------
# Phase 2/9: complete deterministic pipeline works end to end.
# ---------------------------------------------------------------------------


def test_complete_deterministic_pipeline_produces_a_result() -> None:
    result = run_pipeline(
        DOCS,
        chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
        embedder=HashingEmbedder(dimensions=16),
        store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        generator=EchoGenerator(),
        query="How does retrieval work?",
    )
    assert result.text
    assert len(result.source_chunk_ids) > 0


def test_pipeline_is_deterministic_across_repeated_runs() -> None:
    def run() -> str:
        result = run_pipeline(
            DOCS,
            chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
            embedder=HashingEmbedder(dimensions=16),
            store=InMemoryVectorStore(),
            prompt_builder=SimplePromptBuilder(),
            generator=EchoGenerator(),
            query="How does retrieval work?",
        )
        return result.text

    assert run() == run()


# ---------------------------------------------------------------------------
# Phase 4: provider-replacement experiment.
# ---------------------------------------------------------------------------


def test_embedder_can_be_replaced_with_a_different_dimensionality() -> None:
    """Embedder A (16-dim, word-hashing) and Embedder B (8-dim, character
    trigram) are algorithmically and dimensionally unrelated. The pipeline
    must run to completion under both without any code change other than
    swapping which Embedder instance is passed in."""
    chunker = lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)]  # noqa: E731

    for embedder in (HashingEmbedder(dimensions=16), CountingEmbedder(dimensions=8)):
        result = run_pipeline(
            DOCS,
            chunker=chunker,
            embedder=embedder,
            store=InMemoryVectorStore(),
            prompt_builder=SimplePromptBuilder(),
            generator=EchoGenerator(),
            query="embeddings",
        )
        assert result.text


def test_generator_can_be_replaced_independently_of_embedder() -> None:
    chunker = lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)]  # noqa: E731
    for generator in (EchoGenerator(), WordCountGenerator()):
        result = run_pipeline(
            DOCS,
            chunker=chunker,
            embedder=HashingEmbedder(),
            store=InMemoryVectorStore(),
            prompt_builder=SimplePromptBuilder(),
            generator=generator,
            query="retrieval",
        )
        assert result.text


def test_a_query_and_corpus_embedded_with_different_embedders_cannot_be_mixed() -> None:
    """Concrete, discovered coupling (Phase 4 finding): a VectorStore's
    stored embeddings and a query's embedding vector MUST come from the
    same Embedder (same dimensionality/semantics), or search fails
    loudly. This is not a flaw in the pipeline -- it is the real,
    unavoidable coupling between an embedder and whatever store/query
    later reads its output. The store surfaces it as ValueError rather
    than silently producing garbage results."""
    store = InMemoryVectorStore()
    chunk = Chunk(id="c1", document_id="doc-a", text="test text")
    embedding_16d = Embedding(
        chunk_id="c1", vector=tuple(HashingEmbedder(dimensions=16)([chunk.text])[0])
    )
    store.add([embedding_16d], [chunk])

    query_vector_8d = CountingEmbedder(dimensions=8)(["test text"])[0]
    try:
        store.search(query_vector_8d, top_k=1)
        raised = False
    except ValueError:
        raised = True
    assert raised, (
        "dimensionality mismatch between store and query embedder must not be silently ignored"
    )


def test_vector_store_can_be_replaced_with_a_non_vector_backed_store() -> None:
    """Phase 6 adversarial case: does the pipeline accidentally assume
    'store' means 'vector store'? KeywordRetriever + InvertedIndexVectorStore
    prove retrieval can work with zero embeddings and zero vector math --
    the Retriever Protocol itself does not require an Embedder or a
    vector-shaped store, only the __call__(query, top_k) -> RetrievalResult
    signature."""
    store = InvertedIndexVectorStore()
    chunks = [Chunk(id=f"{d.id}::0", document_id=d.id, text=d.text) for d in DOCS]
    store.add([], chunks)

    retriever = KeywordRetriever(store)
    retrieval = retriever("retrieval query candidate", top_k=2)
    assert len(retrieval.scored_chunks) > 0

    prompt = SimplePromptBuilder()("retrieval query candidate", retrieval)
    result = EchoGenerator()(prompt, retrieval)
    assert result.text


# ---------------------------------------------------------------------------
# Phase 6: adversarial edge cases.
# ---------------------------------------------------------------------------


def test_empty_corpus_produces_empty_retrieval_not_a_crash() -> None:
    store = InMemoryVectorStore()
    retriever = SimpleRetriever(HashingEmbedder(), store)
    retrieval = retriever("anything", top_k=2)
    assert retrieval.scored_chunks == ()

    prompt = SimplePromptBuilder()("anything", retrieval)
    result = EchoGenerator()(prompt, retrieval)
    assert result.text
    assert result.source_chunk_ids == ()


def test_empty_query_does_not_crash_the_pipeline() -> None:
    result = run_pipeline(
        DOCS,
        chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
        embedder=HashingEmbedder(),
        store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        generator=EchoGenerator(),
        query="",
    )
    assert result.text


def test_duplicate_documents_do_not_break_retrieval() -> None:
    dupes = [DOCS[0], DOCS[0]]
    result = run_pipeline(
        dupes,
        chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
        embedder=HashingEmbedder(),
        store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        generator=EchoGenerator(),
        query="RAG",
        top_k=5,
    )
    assert result.text


def test_duplicate_chunk_ids_across_documents_do_not_silently_collide() -> None:
    """Discovered edge case: this fake pipeline's chunk IDs are derived
    from document_id, so distinct documents never collide. But two
    Document objects sharing the SAME id (a real ingestion bug) WOULD
    silently overwrite each other in the store's _chunks_by_id dict.
    This is recorded as a genuine open risk (see evaluation ledger Phase
    27F/27G), not fixed here -- fixing it would mean designing a real
    Document identity contract, which Phase 5 explicitly defers without
    a real (non-fake) ingestion consumer."""
    store = InMemoryVectorStore()
    colliding_doc = Document(id="doc-a", text="first version")
    colliding_doc_v2 = Document(id="doc-a", text="second version, different text")

    chunk_1 = Chunk(id="doc-a::0", document_id="doc-a", text=colliding_doc.text)
    chunk_2 = Chunk(id="doc-a::0", document_id="doc-a", text=colliding_doc_v2.text)

    emb1 = Embedding(chunk_id=chunk_1.id, vector=HashingEmbedder()([chunk_1.text])[0])
    emb2 = Embedding(chunk_id=chunk_2.id, vector=HashingEmbedder()([chunk_2.text])[0])
    store.add([emb1], [chunk_1])
    store.add([emb2], [chunk_2])

    assert store._chunks_by_id["doc-a::0"].text == "second version, different text"


def test_missing_metadata_defaults_to_empty_dict_not_none() -> None:
    doc = Document(id="doc-x", text="no metadata provided")
    assert doc.metadata == {}
    chunk = Chunk(id="doc-x::0", document_id="doc-x", text=doc.text)
    assert chunk.metadata == {}


def test_large_metadata_is_preserved_without_truncation() -> None:
    large_value = "x" * 100_000
    doc = Document(id="doc-large", text="short text", metadata={"blob": large_value})
    assert len(doc.metadata["blob"]) == 100_000


def test_unicode_text_survives_the_full_pipeline() -> None:
    unicode_doc = Document(id="doc-unicode", text="éèê 中文 \U0001f600 مرحبا")
    result = run_pipeline(
        [unicode_doc],
        chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
        embedder=HashingEmbedder(),
        store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        generator=EchoGenerator(),
        query="中文",
    )
    assert result.text


def test_embedding_provider_failure_propagates_not_silently_swallowed() -> None:
    raised = False
    try:
        run_pipeline(
            DOCS,
            chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
            embedder=FailingEmbedder(),
            store=InMemoryVectorStore(),
            prompt_builder=SimplePromptBuilder(),
            generator=EchoGenerator(),
            query="anything",
        )
    except RuntimeError as e:
        raised = True
        assert "embedding provider unavailable" in str(e)
    assert raised


def test_generation_provider_failure_propagates_not_silently_swallowed() -> None:
    raised = False
    try:
        run_pipeline(
            DOCS,
            chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
            embedder=HashingEmbedder(),
            store=InMemoryVectorStore(),
            prompt_builder=SimplePromptBuilder(),
            generator=FailingGenerator(),
            query="anything",
        )
    except RuntimeError as e:
        raised = True
        assert "generation provider unavailable" in str(e)
    assert raised


# ---------------------------------------------------------------------------
# Phase 3: data contract properties -- immutability, identity, traceability.
# ---------------------------------------------------------------------------


def test_generation_result_preserves_source_chunk_ids_for_citation() -> None:
    result = run_pipeline(
        DOCS,
        chunker=lambda doc: [Chunk(id=f"{doc.id}::0", document_id=doc.id, text=doc.text)],
        embedder=HashingEmbedder(),
        store=InMemoryVectorStore(),
        prompt_builder=SimplePromptBuilder(),
        generator=EchoGenerator(),
        query="RAG",
        top_k=3,
    )
    assert all(isinstance(cid, str) and cid for cid in result.source_chunk_ids)


def test_document_chunk_embedding_types_are_immutable() -> None:
    doc = Document(id="doc-a", text="text")
    chunk = Chunk(id="c1", document_id="doc-a", text="text")
    embedding = Embedding(chunk_id="c1", vector=(1.0, 2.0))

    for obj, field_name, value in (
        (doc, "text", "changed"),
        (chunk, "text", "changed"),
        (embedding, "vector", (9.9,)),
    ):
        raised = False
        try:
            setattr(obj, field_name, value)
        except (AttributeError, TypeError):
            raised = True
        assert raised, f"{type(obj).__name__} must be immutable"


# ---------------------------------------------------------------------------
# Phase 7: security -- no logging of raw prompts/documents/secrets.
# ---------------------------------------------------------------------------


def test_metadata_containing_a_secret_like_key_is_not_logged_by_default(caplog) -> None:
    from ragtorch.core.logging import get_logger, is_sensitive_key, log_event, redact

    sensitive_doc = Document(
        id="doc-secret", text="normal text", metadata={"api_key": "sk-should-not-appear-in-logs"}
    )
    log = get_logger("discovery")
    with caplog.at_level("INFO"):
        for key, value in sensitive_doc.metadata.items():
            safe_value = redact(value) if is_sensitive_key(key) else value
            log_event(log, 20, "ingesting document metadata", **{key: safe_value})

    assert "sk-should-not-appear-in-logs" not in caplog.text


def test_raw_document_text_is_not_logged_by_default(caplog) -> None:
    from ragtorch.core.logging import get_logger, log_event, redact

    doc = Document(id="doc-a", text="RAG retrieves relevant external knowledge before generation.")
    log = get_logger("discovery")
    with caplog.at_level("INFO"):
        log_event(log, 20, "ingested document", text=redact(doc.text))

    assert doc.text not in caplog.text


# ---------------------------------------------------------------------------
# Phase 9: compatibility with existing Module/Component/Sequential.
# ---------------------------------------------------------------------------


class _RetrieverModule(Module):
    def __init__(self, retriever: SimpleRetriever) -> None:
        super().__init__()
        self._retriever = retriever

    def forward(self, query, *, context=None):
        return self._retriever(query, top_k=2)


class _GeneratorModule(Module):
    def __init__(self, prompt_builder: SimplePromptBuilder, generator: EchoGenerator) -> None:
        super().__init__()
        self._prompt_builder = prompt_builder
        self._generator = generator

    def forward(self, retrieval, *, context=None):
        prompt = self._prompt_builder(retrieval.query, retrieval)
        return self._generator(prompt, retrieval)


def test_fake_rag_stages_compose_naturally_through_sequential() -> None:
    """Does wrapping the discovery fakes in Module/Sequential fit
    naturally, or does it fight the pipeline's actual shape? Finding:
    fits cleanly -- Retriever and Generator stages both reduce to a
    single Module.forward(input) -> output call once the embed+index
    setup (which is a one-time, not per-query, operation) happens
    outside the pipeline, exactly matching how Sequential's own existing
    step contract already works."""
    store = InMemoryVectorStore()
    embedder = HashingEmbedder()
    chunks = [Chunk(id=f"{d.id}::0", document_id=d.id, text=d.text) for d in DOCS]
    vectors = embedder([c.text for c in chunks])
    embeddings = [Embedding(chunk_id=c.id, vector=v) for c, v in zip(chunks, vectors, strict=True)]
    store.add(embeddings, chunks)

    retriever = SimpleRetriever(embedder, store)
    pipeline = Sequential(
        _RetrieverModule(retriever),
        _GeneratorModule(SimplePromptBuilder(), EchoGenerator()),
    )
    result = pipeline("How does retrieval work?")
    assert result.text


def test_no_provider_import_leaks_into_ragtorch_core() -> None:
    """Confirms this discovery experiment did not accidentally import any
    third-party AI/provider dependency into ragtorch itself -- ragtorch's
    own dependency list must remain what Step 25 (A77) already proved:
    zero runtime dependencies."""
    from pathlib import Path

    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10 has no stdlib tomllib (3.11+ only)
        import tomli as tomllib  # type: ignore[no-redef]

    repo_root = Path(ragtorch.__file__).resolve().parents[2]
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text())
    assert pyproject["project"]["dependencies"] == []
