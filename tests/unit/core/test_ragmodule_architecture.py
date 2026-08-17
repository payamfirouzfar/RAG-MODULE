"""Unit tests for RAGModule.from_graph (ADR-021).

Organized around the ADR-021 test matrix (RM/COMPAT), not as an
independent collection of examples. Delegated behavior (graph
validation, execution, context threading) is tested at the boundary
-- proving RAGModule.from_graph correctly delegates to Block -- not
re-implementing Block's own already-tested invariants.
"""

from __future__ import annotations

import pytest

from ragtorch.core.block import Block
from ragtorch.core.component import Component
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError, ValidationError
from ragtorch.core.module import Module, RAGModule
from ragtorch.core.ports import InputPort, OutputPort
from ragtorch.core.sequential import Sequential


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


def linear_graph() -> CompositionGraph:
    return CompositionGraph(
        nodes=(
            GraphNode(id="add", component=AddOne()),
            GraphNode(id="mul", component=MultiplyTwo()),
        ),
        connections=(
            Connection(
                source_node_id="add",
                source_port=OutputPort(name="out", type=int),
                target_node_id="mul",
                target_port=InputPort(name="in", type=int),
            ),
        ),
    )


# --- Construction / type -------------------------------------------------


def test_rm_02_from_graph_exists() -> None:
    assert hasattr(RAGModule, "from_graph")


def test_rm_03_from_graph_returns_ragmodule() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")
    assert isinstance(architecture, RAGModule)


def test_rm_04_from_graph_returns_module() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")
    assert isinstance(architecture, Module)


def test_rm_05_missing_input_node_keyword_is_type_error() -> None:
    with pytest.raises(TypeError):
        RAGModule.from_graph(linear_graph(), output_node="mul")  # type: ignore[call-arg]


def test_rm_06_missing_output_node_keyword_is_type_error() -> None:
    with pytest.raises(TypeError):
        RAGModule.from_graph(linear_graph(), input_node="add")  # type: ignore[call-arg]


def test_rm_07_invalid_input_node_delegates_to_block_validation() -> None:
    with pytest.raises(ValidationError, match="input_node"):
        RAGModule.from_graph(linear_graph(), input_node="does-not-exist", output_node="mul")


def test_rm_08_invalid_output_node_delegates_to_block_validation() -> None:
    with pytest.raises(ValidationError, match="output_node"):
        RAGModule.from_graph(linear_graph(), input_node="add", output_node="does-not-exist")


# --- Registration ----------------------------------------------------------


def test_block_registered_exactly_once() -> None:
    """Regression guard for the double-registration hazard found during
    17C/17D: Module.__setattr__ auto-registers any Module-valued
    attribute, so calling register_module() explicitly in addition to
    assigning self._block would register the same child twice."""
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")

    children = list(architecture.named_children())

    assert len(children) == 1
    assert children[0][0] == "_block"
    assert isinstance(children[0][1], Block)


def test_from_graph_supports_module_inspection() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")

    snapshot = architecture.snapshot()
    inspection = architecture.inspect()

    assert snapshot is not None
    assert "_block" in inspection


# --- Execution ---------------------------------------------------------


def test_rm_09_simple_graph_executes_correctly() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")
    assert architecture(2) == 6


def test_rm_10_block_as_graph_node_inside_from_graph() -> None:
    inner = Block(linear_graph(), input_node="add", output_node="mul")
    outer_graph = CompositionGraph(nodes=(GraphNode(id="inner", component=inner),), connections=())
    architecture = RAGModule.from_graph(outer_graph, input_node="inner", output_node="inner")

    assert architecture(2) == 6


def test_rm_11_from_graph_result_can_be_a_graph_node_component() -> None:
    inner_graph = CompositionGraph(nodes=(GraphNode(id="add", component=AddOne()),), connections=())
    architecture = RAGModule.from_graph(inner_graph, input_node="add", output_node="add")

    outer_graph = CompositionGraph(
        nodes=(GraphNode(id="arch", component=architecture),), connections=()
    )
    outer_block = Block(outer_graph, input_node="arch", output_node="arch")

    assert outer_block(2) == 3


def test_rm_12_from_graph_result_works_as_sequential_child() -> None:
    inner_graph = CompositionGraph(nodes=(GraphNode(id="add", component=AddOne()),), connections=())
    architecture = RAGModule.from_graph(inner_graph, input_node="add", output_node="add")

    pipeline = Sequential(architecture)

    assert pipeline(5) == 6


# --- Context ---------------------------------------------------------------


def test_rm_13_context_preserved() -> None:
    context = ExecutionContext(metadata={"trace": "root"})
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")

    assert architecture(2, context=context) == 6


def test_rm_14_no_context_still_works() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")
    assert architecture(2) == 6


# --- Failure -------------------------------------------------------------


def test_rm_15_component_failure_propagates_as_execution_error() -> None:
    graph = CompositionGraph(nodes=(GraphNode(id="boom", component=Boom()),), connections=())
    architecture = RAGModule.from_graph(graph, input_node="boom", output_node="boom")

    with pytest.raises(ExecutionError):
        architecture("input")


def test_rm_16_original_exception_reachable_via_cause_chain() -> None:
    """Corrected contract (ADR-021 Q8, found during 17C/17D): NOT
    exc.__cause__ is error directly. A bare RAGModule.from_graph(...)
    call wraps twice -- once by _GraphBackedRAGModule's own
    Module.__call__, once by Block's own Module.__call__ (the same
    universal, existing convention Sequential-of-Module nesting
    already has) -- so the original exception is reachable at
    exc.__cause__.__cause__."""
    graph = CompositionGraph(nodes=(GraphNode(id="boom", component=Boom()),), connections=())
    architecture = RAGModule.from_graph(graph, input_node="boom", output_node="boom")

    with pytest.raises(ExecutionError) as exc_info:
        architecture("input")

    assert isinstance(exc_info.value.__cause__, ExecutionError)
    assert isinstance(exc_info.value.__cause__.__cause__, ValueError)


def test_failure_wrap_depth_increases_by_one_when_nested_in_sequential() -> None:
    graph = CompositionGraph(nodes=(GraphNode(id="boom", component=Boom()),), connections=())
    architecture = RAGModule.from_graph(graph, input_node="boom", output_node="boom")
    pipeline = Sequential(architecture)

    with pytest.raises(ExecutionError) as exc_info:
        pipeline("input")

    # Sequential -> _GraphBackedRAGModule -> Block -> ValueError: three hops
    assert isinstance(exc_info.value.__cause__, ExecutionError)
    assert isinstance(exc_info.value.__cause__.__cause__, ExecutionError)
    assert isinstance(exc_info.value.__cause__.__cause__.__cause__, ValueError)


# --- Backward compatibility -------------------------------------------------


def test_rm_01_existing_subclass_pattern_still_works() -> None:
    class MyRAG(RAGModule):
        def forward(self, input: int) -> int:
            return input + 100

    instance = MyRAG()

    assert instance(1) == 101
    assert isinstance(instance, RAGModule)
    assert isinstance(instance, Module)


def test_component_protocol_satisfied() -> None:
    architecture = RAGModule.from_graph(linear_graph(), input_node="add", output_node="mul")
    assert isinstance(architecture, Component)


# --- Provider independence -------------------------------------------------


def test_rm_17_module_has_no_provider_imports() -> None:
    import ast
    import inspect as inspect_module

    from ragtorch.core import module as module_module

    source = inspect_module.getsource(module_module)
    tree = ast.parse(source)

    forbidden_substrings = ("openai", "anthropic", "langchain", "llamaindex", "ollama")

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    for module_name in imported_modules:
        lowered = module_name.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), (
            f"module.py must not import {module_name!r}"
        )
