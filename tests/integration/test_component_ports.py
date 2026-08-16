"""Integration/contract tests for Component ports (ADR-011).

Proves compatibility behavior across two independent, fake component
boundaries - no LLM, database, vector store, network, or provider
dependency."""

from __future__ import annotations

import pytest

from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, check_connection, is_compatible


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


# --- check_connection() (ADR-014) ---------------------------------------


def test_check_connection_passes_retriever_to_reranker() -> None:
    assert check_connection(FakeRetriever.output_port, FakeReranker.input_port) is None


def test_check_connection_passes_reranker_to_reranker() -> None:
    assert check_connection(FakeReranker.output_port, FakeReranker.input_port) is None


def test_check_connection_rejects_retriever_to_generator() -> None:
    with pytest.raises(ValidationError):
        check_connection(FakeRetriever.output_port, FakeGenerator.input_port)


# --- Connection (ADR-015) -------------------------------------------------


def test_connection_constructs_for_retriever_to_reranker() -> None:
    connection = Connection(
        source_node_id="retriever",
        source_port=FakeRetriever.output_port,
        target_node_id="reranker",
        target_port=FakeReranker.input_port,
    )
    assert connection.source_node_id == "retriever"
    assert connection.target_node_id == "reranker"


def test_connection_constructs_for_reranker_to_generator() -> None:
    connection = Connection(
        source_node_id="reranker",
        source_port=OutputPort(name="prompt", type=str),
        target_node_id="generator",
        target_port=FakeGenerator.input_port,
    )
    assert connection.source_node_id == "reranker"
    assert connection.target_node_id == "generator"


def test_connection_rejects_retriever_to_generator() -> None:
    with pytest.raises(ValidationError):
        Connection(
            source_node_id="retriever",
            source_port=FakeRetriever.output_port,
            target_node_id="generator",
            target_port=FakeGenerator.input_port,
        )
