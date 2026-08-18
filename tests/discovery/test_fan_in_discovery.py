"""Step 33 discovery: does ragtorch's execution machinery already
support fan-in (multiple upstream results feeding one downstream
step), independent of CompositionGraph's fan-in <= 1 restriction?

These are characterization tests recording a real finding, not a new
production feature -- no production code changed as a result of this
step (see evaluation/step33-evaluation.md for the full decision
record). Kept here rather than deleted so a future step revisiting this
question does not have to rediscover it from scratch.

Human-readable scenario: dense retrieval and BM25/lexical retrieval
over three tiny documents, fused with rrf() -- the same shape
HybridRetriever (examples/rag_consumer/) already handles directly in
plain Python, used here to demonstrate that the raw executor could
express it too, without CompositionGraph's involvement.
"""

from __future__ import annotations

import pytest

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.execution import SequentialExecutor
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep
from ragtorch.core.ports import InputPort, OutputPort
from ragtorch.retrieval import rrf

DOCUMENTS = {
    "python": "Python is a programming language.",
    "paris": "Paris is the capital of France.",
    "guido": "Python was created by Guido van Rossum.",
}
QUERY = "Who created Python?"


class _FakeComponent:
    """Minimal Component-shaped stand-in -- no real embedding/BM25
    machinery needed to demonstrate the executor's own behavior."""

    def __init__(self, name: str, fn) -> None:
        self.name = name
        self.component_type = "fake"
        self._fn = fn

    def __call__(self, value, *, context=None):
        return self._fn(value)


def test_execution_plan_and_executor_already_support_fan_in_directly():
    """FINDING: ExecutionStep.dependencies is already tuple[str, ...]
    (plural) and SequentialExecutor already hands a StepHandler the
    full StepExecutionContext (every prior step's result, keyed by
    node_id) -- a fusion step can already read multiple upstream
    results with zero changes to ExecutionPlan/SequentialExecutor.
    Built by hand here (not via CompositionGraph/plan()) because
    CompositionGraph itself is what currently forbids constructing
    this shape -- see test_composition_graph_rejects_fan_in below."""
    plan = ExecutionPlan(
        steps=(
            ExecutionStep(node_id="dense", dependencies=()),
            ExecutionStep(node_id="bm25", dependencies=()),
            ExecutionStep(node_id="fusion", dependencies=("dense", "bm25")),
        )
    )

    # dense retrieval ranks "guido" doc last; BM25 ranks it first --
    # a human can see fusion should pull "guido" up via both signals.
    def handler(step, context):
        if step.node_id == "dense":
            return ["python", "paris", "guido"]
        if step.node_id == "bm25":
            return ["guido", "python", "paris"]
        if step.node_id == "fusion":
            dense_ids = context.results["dense"]
            bm25_ids = context.results["bm25"]
            return rrf([dense_ids, bm25_ids])
        raise AssertionError(step.node_id)

    result = SequentialExecutor().execute(plan, handler)

    fused = result.values["fusion"]
    assert fused[0].item in {"python", "guido"}  # both reinforced by two signals
    assert {r.item for r in fused} == {"python", "paris", "guido"}


def test_composition_graph_rejects_fan_in():
    """FINDING: CompositionGraph is the ONLY layer that rejects
    fan-in -- confirmed directly, not assumed. ExecutionPlan/
    SequentialExecutor (above) have no such restriction."""
    dense_node = GraphNode(id="dense", component=_FakeComponent("dense", lambda x: x))
    bm25_node = GraphNode(id="bm25", component=_FakeComponent("bm25", lambda x: x))
    fusion_node = GraphNode(id="fusion", component=_FakeComponent("fusion", lambda x: x))

    dense_out = OutputPort(name="out", type=list)
    bm25_out = OutputPort(name="out", type=list)
    fusion_in = InputPort(name="in", type=list)

    dense_to_fusion = Connection(
        source_node_id="dense",
        source_port=dense_out,
        target_node_id="fusion",
        target_port=fusion_in,
    )
    bm25_to_fusion = Connection(
        source_node_id="bm25", source_port=bm25_out, target_node_id="fusion", target_port=fusion_in
    )

    with pytest.raises(ValidationError, match="fan-in is limited to one connection"):
        CompositionGraph(
            nodes=(dense_node, bm25_node, fusion_node),
            connections=(dense_to_fusion, bm25_to_fusion),
        )


def test_hybrid_retriever_already_solves_this_without_the_graph():
    """FINDING: the real consumer's actual HybridRetriever (examples/
    rag_consumer/src/hybrid_retriever.py) already performs this exact
    dense+lexical fan-in in plain Python inside one Module.forward(),
    with no graph, no ExecutionPlan, no executor, and no aggregation
    convention to invent. This is the comparison point the Step 33
    decision (evaluation/step33-evaluation.md) is based on: expressing
    the same fusion at the CompositionGraph/Block level would require
    inventing a value-packaging convention for multiple dependencies
    (Block.forward()'s handler currently unpacks exactly one
    dependency: `(dependency,) = step.dependencies`) without reducing
    the fusion logic itself, which is identical either way."""
    dense_ids = ["python", "paris", "guido"]
    bm25_ids = ["guido", "python", "paris"]
    fused = rrf([dense_ids, bm25_ids])

    assert {r.item for r in fused} == {"python", "paris", "guido"}
    # No CompositionGraph, no Block, no ExecutionPlan, no Executor
    # were needed to reach this result -- exactly what
    # HybridRetriever.forward() already does.
