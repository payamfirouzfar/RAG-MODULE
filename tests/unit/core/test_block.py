"""Unit tests for Block (ADR-020).

Organized around the ADR-020 test matrix (CONSTRUCT/CONTRACT/EXEC/
NEST/FAIL/COMPAT), not as an independent collection of examples.
"""

from __future__ import annotations

import pytest

from ragtorch.core.block import Block
from ragtorch.core.component import Component
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError, ValidationError
from ragtorch.core.module import Module
from ragtorch.core.ports import InputPort, OutputPort


class AddOne:
    name = "add_one"
    component_type = "AddOne"

    def __call__(self, value: int, *, context: ExecutionContext | None = None) -> int:
        return value + 1


class MultiplyTwo:
    name = "multiply_two"
    component_type = "MultiplyTwo"

    def __call__(self, value: int, *, context: ExecutionContext | None = None) -> int:
        return value * 2


class Boom:
    name = "boom"
    component_type = "Boom"

    def __call__(self, value: object, *, context: ExecutionContext | None = None) -> object:
        raise ValueError("kaboom")


class RecordingComponent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.component_type = "RecordingComponent"
        self.inputs: list[object] = []
        self.contexts: list[ExecutionContext | None] = []

    def __call__(self, value: object, *, context: ExecutionContext | None = None) -> object:
        self.inputs.append(value)
        self.contexts.append(context)
        return value


def connection(source_id: str, target_id: str, *, port_type: type = int) -> Connection:
    return Connection(
        source_node_id=source_id,
        source_port=OutputPort(name=f"out_{source_id}", type=port_type),
        target_node_id=target_id,
        target_port=InputPort(name=f"in_{target_id}", type=port_type),
    )


def linear_graph() -> CompositionGraph:
    return CompositionGraph(
        nodes=(
            GraphNode(id="add", component=AddOne()),
            GraphNode(id="mul", component=MultiplyTwo()),
        ),
        connections=(connection("add", "mul"),),
    )


def single_node_graph() -> CompositionGraph:
    return CompositionGraph(nodes=(GraphNode(id="only", component=AddOne()),), connections=())


# --- CONSTRUCT ---------------------------------------------------------


def test_construct_01_block_constructs_with_valid_linear_graph() -> None:
    graph = linear_graph()
    block = Block(graph, input_node="add", output_node="mul")

    assert block.graph is graph
    assert block.input_node == "add"
    assert block.output_node == "mul"


def test_construct_02_nonexistent_input_node_raises() -> None:
    graph = linear_graph()
    with pytest.raises(ValidationError, match="input_node"):
        Block(graph, input_node="does-not-exist", output_node="mul")


def test_construct_03_nonexistent_output_node_raises() -> None:
    graph = linear_graph()
    with pytest.raises(ValidationError, match="output_node"):
        Block(graph, input_node="add", output_node="does-not-exist")


def test_construct_04_empty_graph_rejected() -> None:
    empty = CompositionGraph(nodes=(), connections=())
    with pytest.raises(ValidationError):
        Block(empty, input_node="a", output_node="b")


def test_construct_05_multi_dependency_node_rejected() -> None:
    graph = CompositionGraph(
        nodes=(
            GraphNode(id="a", component=AddOne()),
            GraphNode(id="b", component=AddOne()),
            GraphNode(id="c", component=AddOne()),
        ),
        connections=(
            Connection(
                source_node_id="a",
                source_port=OutputPort(name="out_a", type=int),
                target_node_id="c",
                target_port=InputPort(name="in_c_a", type=int),
            ),
            Connection(
                source_node_id="b",
                source_port=OutputPort(name="out_b", type=int),
                target_node_id="c",
                target_port=InputPort(name="in_c_b", type=int),
            ),
        ),
    )
    # c has two dependencies (a and b); c is not input_node
    with pytest.raises(ValidationError, match="exactly one dependency"):
        Block(graph, input_node="a", output_node="c")


def test_construct_rejects_non_composition_graph() -> None:
    with pytest.raises(TypeError):
        Block("not a graph", input_node="a", output_node="b")  # type: ignore[arg-type]


# --- CONTRACT ---------------------------------------------------------


def test_contract_01_block_satisfies_component_protocol() -> None:
    block = Block(linear_graph(), input_node="add", output_node="mul")
    assert isinstance(block, Component)


def test_contract_02_block_name_matches_module_convention() -> None:
    block = Block(linear_graph(), input_node="add", output_node="mul")
    assert block.name == type(block).__name__


def test_contract_03_graph_property_is_identity_not_copy() -> None:
    graph = linear_graph()
    block = Block(graph, input_node="add", output_node="mul")
    assert block.graph is graph


# --- EXEC ---------------------------------------------------------------


def test_exec_01_single_node_block_returns_component_output() -> None:
    block = Block(single_node_graph(), input_node="only", output_node="only")
    assert block(2) == 3


def test_exec_02_linear_chain_composes_correctly() -> None:
    block = Block(linear_graph(), input_node="add", output_node="mul")
    assert block(2) == 6


def test_exec_03_plan_is_rederived_each_call_not_cached_incorrectly() -> None:
    a = RecordingComponent("a")
    b = RecordingComponent("b")
    graph = CompositionGraph(
        nodes=(GraphNode(id="a", component=a), GraphNode(id="b", component=b)),
        connections=(connection("a", "b", port_type=object),),
    )
    block = Block(graph, input_node="a", output_node="b")

    block(1)
    block(2)

    assert a.inputs == [1, 2]
    assert b.inputs == [1, 2]


def test_exec_04_input_node_receives_block_input() -> None:
    recorder = RecordingComponent("entry")
    graph = CompositionGraph(nodes=(GraphNode(id="entry", component=recorder),), connections=())
    block = Block(graph, input_node="entry", output_node="entry")

    block("question")

    assert recorder.inputs == ["question"]


def test_exec_05_downstream_receives_upstream_result() -> None:
    block = Block(linear_graph(), input_node="add", output_node="mul")
    # 2 -> add -> 3 -> mul -> 6
    assert block(2) == 6


def test_exec_06_output_node_determines_result_not_last_step() -> None:
    """A 3-node chain where output_node is the MIDDLE node, not the
    topologically last one -- proves Block returns output_node's
    result specifically, never assumes "last executed step"."""
    graph = CompositionGraph(
        nodes=(
            GraphNode(id="a", component=AddOne()),
            GraphNode(id="b", component=MultiplyTwo()),
            GraphNode(id="c", component=AddOne()),
        ),
        connections=(connection("a", "b"), connection("b", "c")),
    )
    # output_node = "b" (middle), not "c" (last)
    block = Block(graph, input_node="a", output_node="b")
    # 2 -> a(+1) -> 3 -> b(*2) -> 6 [returned, c never affects result]
    assert block(2) == 6


# --- NEST ---------------------------------------------------------------


class Doubler(Module):
    def forward(self, value: int, *, context: ExecutionContext | None = None) -> int:
        return value * 2


def test_nest_01_block_as_graph_node_component_in_outer_graph() -> None:
    inner = Block(linear_graph(), input_node="add", output_node="mul")
    outer_graph = CompositionGraph(nodes=(GraphNode(id="inner", component=inner),), connections=())
    outer = Block(outer_graph, input_node="inner", output_node="inner")

    assert outer(2) == 6


def test_nest_02_block_as_sequential_child_preserves_context_ancestry() -> None:
    recorder = RecordingComponent("rec")
    graph = CompositionGraph(nodes=(GraphNode(id="r", component=recorder),), connections=())
    block = Block(graph, input_node="r", output_node="r")

    from ragtorch.core.sequential import Sequential

    seq = Sequential(Doubler(), block)
    root_context = ExecutionContext(metadata={"trace": "root"})

    result = seq(3, context=root_context)

    assert result == 6
    observed_context = recorder.contexts[0]
    assert observed_context is not None
    assert observed_context.run_id != root_context.run_id
    assert observed_context.parent_run_id == root_context.run_id


def test_nest_03_block_containing_block_two_levels() -> None:
    inner = Block(linear_graph(), input_node="add", output_node="mul")
    middle_graph = CompositionGraph(nodes=(GraphNode(id="inner", component=inner),), connections=())
    middle = Block(middle_graph, input_node="inner", output_node="inner")
    outer_graph = CompositionGraph(
        nodes=(GraphNode(id="middle", component=middle),), connections=()
    )
    outer = Block(outer_graph, input_node="middle", output_node="middle")

    assert outer(2) == 6


# --- FAIL ---------------------------------------------------------------


def test_fail_01_component_failure_propagates_as_execution_error() -> None:
    graph = CompositionGraph(nodes=(GraphNode(id="boom", component=Boom()),), connections=())
    block = Block(graph, input_node="boom", output_node="boom")

    with pytest.raises(ExecutionError) as exc_info:
        block("input")

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_fail_02_downstream_execution_stops_after_failure() -> None:
    recorder = RecordingComponent("after")
    graph = CompositionGraph(
        nodes=(
            GraphNode(id="a", component=AddOne()),
            GraphNode(id="boom", component=Boom()),
            GraphNode(id="after", component=recorder),
        ),
        connections=(connection("a", "boom"), connection("boom", "after", port_type=object)),
    )
    block = Block(graph, input_node="a", output_node="after")

    with pytest.raises(ExecutionError):
        block(1)

    assert recorder.inputs == []


def test_fail_03_no_new_block_specific_exception_type() -> None:
    """Regression guard: Block must not introduce a Block-specific
    exception type -- failures propagate as the existing ExecutionError,
    matching every other Module subclass exactly (ADR-020 Q10)."""
    graph = CompositionGraph(nodes=(GraphNode(id="boom", component=Boom()),), connections=())
    block = Block(graph, input_node="boom", output_node="boom")

    with pytest.raises(ExecutionError) as exc_info:
        block("x")

    assert type(exc_info.value) is ExecutionError
