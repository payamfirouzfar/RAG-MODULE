"""Integration tests for plan()/ExecutionPlan (ADR-017).

Builds realistic Retriever/Reranker/Generator/Evaluator/Fusion-shaped
compositions - no LLM, database, vector store, network, or provider
dependency."""

from __future__ import annotations

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.execution_plan import plan
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


def test_retriever_reranker_generator_chain_plans_in_order() -> None:
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
    result = plan(graph)
    assert [step.node_id for step in result.steps] == ["retriever", "reranker", "generator"]

    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["retriever"].dependencies == ()
    assert steps_by_id["reranker"].dependencies == ("retriever",)
    assert steps_by_id["generator"].dependencies == ("reranker",)


def test_fan_out_graph_plans_with_shared_dependency() -> None:
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
    result = plan(graph)
    ids = [step.node_id for step in result.steps]
    assert ids.index("retriever") < ids.index("reranker")
    assert ids.index("retriever") < ids.index("evaluator")

    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["reranker"].dependencies == ("retriever",)
    assert steps_by_id["evaluator"].dependencies == ("retriever",)


def test_fusion_graph_with_two_distinct_input_ports_plans_correctly() -> None:
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
    result = plan(graph)
    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["fusion"].dependencies == ("retriever_a", "retriever_b")
