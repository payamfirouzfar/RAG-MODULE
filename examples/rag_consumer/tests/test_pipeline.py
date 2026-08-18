"""Pipeline tests: successful end-to-end execution (through real
ragtorch.ExecutionEngine), missing API key, empty retrieval, generator
failure. No live network / API key used."""

from __future__ import annotations

import pytest
from src.chunking import Chunk
from src.embeddings import HashingEmbedder
from src.generator import GeneratorError, LLMGenerator, OfflineGenerator
from src.pipeline import PipelineState, build_pipeline, run_pipeline
from src.reranker import Reranker
from src.retriever import Retriever
from src.vector_store import InMemoryVectorStore

from ragtorch import ExecutionError, RunStatus


def _build_store_with_content(embedder) -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    chunks = [
        Chunk(
            chunk_id="c1",
            document_id="d1",
            url="http://x/1",
            title="Cats",
            text="Cats are small domesticated mammals.",
            chunk_index=0,
        ),
        Chunk(
            chunk_id="c2",
            document_id="d2",
            url="http://x/2",
            title="Dogs",
            text="Dogs are loyal domesticated companions.",
            chunk_index=0,
        ),
    ]
    vectors = embedder.embed_documents([c.text for c in chunks])
    store.add(chunks, vectors)
    return store


def test_successful_end_to_end_execution():
    embedder = HashingEmbedder(dimensions=32)
    store = _build_store_with_content(embedder)
    retriever = Retriever(embedder, store, top_k=2)
    generator = OfflineGenerator()
    pipeline = build_pipeline(
        retriever=retriever, reranker=None, generator=generator, mode="offline"
    )

    result = run_pipeline(pipeline, "Tell me about cats")

    assert result.run_status == RunStatus.SUCCEEDED
    assert result.answer
    assert isinstance(result.sources, list)
    assert result.trace_render  # a real ragtorch Trace was captured


def test_pipeline_with_reranker_enabled():
    embedder = HashingEmbedder(dimensions=32)
    store = _build_store_with_content(embedder)
    retriever = Retriever(embedder, store, top_k=2)
    generator = OfflineGenerator()
    pipeline = build_pipeline(
        retriever=retriever, reranker=Reranker(), generator=generator, mode="offline"
    )

    result = run_pipeline(pipeline, "Tell me about dogs")
    assert result.run_status == RunStatus.SUCCEEDED


def test_empty_retrieval_produces_insufficient_evidence_answer():
    embedder = HashingEmbedder(dimensions=32)
    store = InMemoryVectorStore()  # empty -- nothing indexed
    retriever = Retriever(embedder, store, top_k=2)
    generator = OfflineGenerator()
    pipeline = build_pipeline(
        retriever=retriever, reranker=None, generator=generator, mode="offline"
    )

    result = run_pipeline(pipeline, "anything")

    assert result.run_status == RunStatus.SUCCEEDED  # empty retrieval is not a failure
    assert result.sources == []
    assert "insufficient" in result.answer.lower()


def test_generator_failure_propagates_as_execution_error(monkeypatch):
    """Verified against the real installed package's failure semantics
    (inspect + direct test during the repository audit): ExecutionEngine
    wraps a Module failure as a raised ExecutionError, not a silently
    swallowed result -- this test confirms the pipeline preserves that
    behavior rather than catching and hiding it."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    embedder = HashingEmbedder(dimensions=32)
    store = _build_store_with_content(embedder)
    retriever = Retriever(embedder, store, top_k=2)
    generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
    pipeline = build_pipeline(retriever=retriever, reranker=None, generator=generator, mode="llm")

    with pytest.raises(ExecutionError):
        run_pipeline(pipeline, "any question")


def test_missing_api_key_raises_generator_error_via_forward(monkeypatch):
    """.forward() bypasses Module.__call__'s exception wrapping and
    surfaces the raw GeneratorError -- see test_generator.py's module
    docstring note for the verified Module.__call__ contract this
    distinction depends on."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    generator = LLMGenerator(provider="openai", model="gpt-4o-mini")
    with pytest.raises(GeneratorError, match="OPENAI_API_KEY"):
        generator.forward(("q", [], "prompt"))


def test_pipeline_state_is_immutable():
    state = PipelineState(question="q")
    with pytest.raises((AttributeError, TypeError)):
        state.question = "changed"
