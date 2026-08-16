"""Integration tests for CompositionGraph (ADR-016).

Builds realistic Retriever/Reranker/Generator/Evaluator/Fusion-shaped
compositions - no LLM, database, vector store, network, or provider
dependency."""

from __future__ import annotations

import pytest

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


def test_retriever_reranker_generator_chain_constructs() -> None:
    retriever = GraphNode(id="retriever", component=FakeComponent())
    reranker = GraphNode(id="reranker", component=FakeComponent())
    generator = GraphNode(id="generator", component=FakeComponent())

    retriever_to_reranker = Connection(
        source_node_id="retriever",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="reranker",
        target_port=InputPort(name="documents", type=list),
    )
    reranker_to_generator = Connection(
        source_node_id="reranker",
        source_port=OutputPort(name="prompt", type=str),
        target_node_id="generator",
        target_port=InputPort(name="prompt", type=str),
    )

    graph = CompositionGraph(
        nodes=(retriever, reranker, generator),
        connections=(retriever_to_reranker, reranker_to_generator),
    )
    assert len(graph.nodes) == 3
    assert len(graph.connections) == 2


def test_retriever_fans_out_to_reranker_and_evaluator() -> None:
    retriever = GraphNode(id="retriever", component=FakeComponent())
    reranker = GraphNode(id="reranker", component=FakeComponent())
    evaluator = GraphNode(id="evaluator", component=FakeComponent())

    to_reranker = Connection(
        source_node_id="retriever",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="reranker",
        target_port=InputPort(name="documents", type=list),
    )
    to_evaluator = Connection(
        source_node_id="retriever",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="evaluator",
        target_port=InputPort(name="documents", type=list),
    )

    graph = CompositionGraph(
        nodes=(retriever, reranker, evaluator),
        connections=(to_reranker, to_evaluator),
    )
    assert len(graph.connections) == 2


def test_two_retrievers_targeting_same_generator_input_port_rejected() -> None:
    retriever_a = GraphNode(id="retriever_a", component=FakeComponent())
    retriever_b = GraphNode(id="retriever_b", component=FakeComponent())
    generator = GraphNode(id="generator", component=FakeComponent())

    a_to_generator = Connection(
        source_node_id="retriever_a",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="generator",
        target_port=InputPort(name="documents", type=list),
    )
    b_to_generator = Connection(
        source_node_id="retriever_b",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="generator",
        target_port=InputPort(name="documents", type=list),
    )

    with pytest.raises(ValidationError, match="fan-in"):
        CompositionGraph(
            nodes=(retriever_a, retriever_b, generator),
            connections=(a_to_generator, b_to_generator),
        )


def test_two_retrievers_targeting_different_fusion_input_ports_allowed() -> None:
    """Proves cardinality is enforced port-level, not node-level."""
    retriever_a = GraphNode(id="retriever_a", component=FakeComponent())
    retriever_b = GraphNode(id="retriever_b", component=FakeComponent())
    fusion = GraphNode(id="fusion", component=FakeComponent())

    a_to_fusion = Connection(
        source_node_id="retriever_a",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="fusion",
        target_port=InputPort(name="inputs_a", type=list),
    )
    b_to_fusion = Connection(
        source_node_id="retriever_b",
        source_port=OutputPort(name="documents", type=list),
        target_node_id="fusion",
        target_port=InputPort(name="inputs_b", type=list),
    )

    graph = CompositionGraph(
        nodes=(retriever_a, retriever_b, fusion),
        connections=(a_to_fusion, b_to_fusion),
    )
    assert len(graph.connections) == 2
