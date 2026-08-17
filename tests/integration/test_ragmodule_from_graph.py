"""Integration test: RAGModule.from_graph composing a RAG-shaped
architecture end-to-end through the public API (ADR-021), and
nesting inside Sequential -- the RAGModule analogue of
test_block_composition.py's scenario.
"""

from __future__ import annotations

import pytest

from ragtorch import (
    Block,
    CompositionGraph,
    Connection,
    ExecutionContext,
    GraphNode,
    InputPort,
    Module,
    OutputPort,
    RAGModule,
    Sequential,
)
from ragtorch.core.errors import ExecutionError


class Retriever:
    name = "retriever"
    component_type = "Retriever"

    def __call__(self, query: str, *, context: ExecutionContext | None = None) -> list[str]:
        return [f"doc-about-{query}", "doc-b"]


class Reranker:
    name = "reranker"
    component_type = "Reranker"

    def __call__(self, docs: list[str], *, context: ExecutionContext | None = None) -> list[str]:
        return list(reversed(docs))


class Generator:
    name = "generator"
    component_type = "Generator"

    def __call__(self, docs: list[str], *, context: ExecutionContext | None = None) -> str:
        return f"answer using {docs}"


class FailingStage:
    name = "failing"
    component_type = "FailingStage"

    def __call__(self, value: object, *, context: ExecutionContext | None = None) -> object:
        raise ValueError("stage exploded")


class Upper(Module):
    def forward(self, value: str, *, context: ExecutionContext | None = None) -> str:
        return value.upper()


def rag_graph() -> CompositionGraph:
    return CompositionGraph(
        nodes=(
            GraphNode(id="retrieve", component=Retriever()),
            GraphNode(id="rerank", component=Reranker()),
            GraphNode(id="generate", component=Generator()),
        ),
        connections=(
            Connection(
                source_node_id="retrieve",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="rerank",
                target_port=InputPort(name="docs", type=list),
            ),
            Connection(
                source_node_id="rerank",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="generate",
                target_port=InputPort(name="docs", type=list),
            ),
        ),
    )


def test_ragmodule_from_graph_rag_shaped_end_to_end() -> None:
    architecture = RAGModule.from_graph(rag_graph(), input_node="retrieve", output_node="generate")

    assert isinstance(architecture, RAGModule)
    result = architecture("What is RAG?")

    assert "answer using" in result
    assert "doc-b" in result


def test_ragmodule_from_graph_nested_inside_sequential_end_to_end() -> None:
    architecture = RAGModule.from_graph(rag_graph(), input_node="retrieve", output_node="generate")
    pipeline = Sequential(Upper(), architecture)

    result = pipeline("what is rag?")

    assert "answer using" in result


def test_ragmodule_from_graph_contains_a_block_node() -> None:
    inner_block = Block(rag_graph(), input_node="retrieve", output_node="generate")
    outer_graph = CompositionGraph(
        nodes=(GraphNode(id="pipeline", component=inner_block),), connections=()
    )
    architecture = RAGModule.from_graph(outer_graph, input_node="pipeline", output_node="pipeline")

    result = architecture("What is RAG?")

    assert "answer using" in result


def test_ragmodule_from_graph_failure_propagates_through_sequential() -> None:
    graph = CompositionGraph(
        nodes=(
            GraphNode(id="retrieve", component=Retriever()),
            GraphNode(id="fail", component=FailingStage()),
        ),
        connections=(
            Connection(
                source_node_id="retrieve",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="fail",
                target_port=InputPort(name="docs", type=list),
            ),
        ),
    )
    architecture = RAGModule.from_graph(graph, input_node="retrieve", output_node="fail")
    pipeline = Sequential(Upper(), architecture)

    with pytest.raises(ExecutionError):
        pipeline("query")
