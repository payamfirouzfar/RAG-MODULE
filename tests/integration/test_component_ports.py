"""Integration/contract tests for Component ports (ADR-011).

Proves compatibility behavior across two independent, fake component
boundaries - no LLM, database, vector store, network, or provider
dependency."""

from __future__ import annotations

from ragtorch.core.ports import InputPort, OutputPort, is_compatible


class FakeRetriever:
    output_port = OutputPort(name="documents", type=list)


class FakeReranker:
    input_port = InputPort(name="documents", type=list)
    output_port = OutputPort(name="documents", type=list)


class FakeGenerator:
    input_port = InputPort(name="prompt", type=str)


def test_retriever_output_can_feed_reranker_input() -> None:
    assert is_compatible(FakeRetriever.output_port, FakeReranker.input_port)


def test_reranker_output_can_feed_another_reranker_input() -> None:
    assert is_compatible(FakeReranker.output_port, FakeReranker.input_port)


def test_incompatible_components_are_rejected() -> None:
    retriever_output = OutputPort(name="documents", type=list)
    generator_input = InputPort(name="prompt", type=str)
    assert not is_compatible(retriever_output, generator_input)


def test_retriever_output_cannot_feed_generator_input() -> None:
    assert not is_compatible(FakeRetriever.output_port, FakeGenerator.input_port)
