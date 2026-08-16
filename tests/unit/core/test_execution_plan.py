"""Unit tests for ExecutionPlan/ExecutionStep/plan() (ADR-017).

Organized around the invariants E1-E12 plus the 13A/13B adversarial
review items, not as an independent collection of examples."""

from __future__ import annotations

import dataclasses

import pytest

from ragtorch.core.component import Component
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.execution_plan import ExecutionPlan, ExecutionStep, plan
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


class ExplodingComponent:
    """Raises if ever called - proves plan() never executes it."""

    name = "exploding"
    component_type = "ExplodingComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        raise AssertionError("MUST NOT EXECUTE")


def node(node_id: str, component: Component[object, object] | None = None) -> GraphNode:
    return GraphNode(id=node_id, component=component or FakeComponent())


def connection(
    source_id: str,
    target_id: str,
    *,
    source_port_name: str = "out",
    target_port_name: str = "in",
    port_type: type = list,
) -> Connection:
    return Connection(
        source_node_id=source_id,
        source_port=OutputPort(name=source_port_name, type=port_type),
        target_node_id=target_id,
        target_port=InputPort(name=target_port_name, type=port_type),
    )


# --- E1/E5/E12: basic construction -------------------------------------


def test_empty_graph_returns_empty_plan() -> None:
    graph = CompositionGraph(nodes=(), connections=())
    assert plan(graph).steps == ()


def test_single_node_returns_single_step() -> None:
    graph = CompositionGraph(nodes=(node("A"),), connections=())
    result = plan(graph)
    assert result.steps == (ExecutionStep(node_id="A", dependencies=()),)


def test_chain_produces_topological_order() -> None:
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("B", "C", source_port_name="o2", target_port_name="i2"),
        ),
    )
    result = plan(graph)
    assert [step.node_id for step in result.steps] == ["A", "B", "C"]


def test_diamond_produces_valid_topological_order() -> None:
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    result = plan(graph)
    ids = [step.node_id for step in result.steps]
    assert set(ids) == {"A", "B", "C", "D"}
    assert ids.index("A") < ids.index("B") < ids.index("D")
    assert ids.index("A") < ids.index("C") < ids.index("D")


def test_disconnected_graph_is_supported() -> None:
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B"),
            connection("C", "D", source_port_name="o2", target_port_name="i2"),
        ),
    )
    result = plan(graph)
    ids = [step.node_id for step in result.steps]
    assert set(ids) == {"A", "B", "C", "D"}
    assert ids.index("A") < ids.index("B")
    assert ids.index("C") < ids.index("D")


# --- Dependency semantics ------------------------------------------------


def test_dependencies_are_direct_predecessors_only() -> None:
    """A -> B -> C: C.dependencies must be ("B",), not ("A", "B")."""
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("B", "C", source_port_name="o2", target_port_name="i2"),
        ),
    )
    result = plan(graph)
    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["C"].dependencies == ("B",)
    assert steps_by_id["B"].dependencies == ("A",)
    assert steps_by_id["A"].dependencies == ()


def test_root_node_has_empty_dependencies() -> None:
    graph = CompositionGraph(nodes=(node("A"), node("B")), connections=(connection("A", "B"),))
    result = plan(graph)
    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["A"].dependencies == ()


def test_diamond_dependencies_contain_both_predecessors() -> None:
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    result = plan(graph)
    steps_by_id = {step.node_id: step for step in result.steps}
    assert steps_by_id["D"].dependencies == ("B", "C")


def test_dependencies_are_deterministically_ordered_by_connection_declaration() -> None:
    """D depends on both B and C; dependencies order must follow the
    order B->D and C->D were declared in graph.connections."""
    graph_forward = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    graph_reversed = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
        ),
    )
    d_forward = next(s for s in plan(graph_forward).steps if s.node_id == "D")
    d_reversed = next(s for s in plan(graph_reversed).steps if s.node_id == "D")
    assert d_forward.dependencies == ("B", "C")
    assert d_reversed.dependencies == ("C", "B")


# --- E11a: time-zero tie-break follows graph.nodes declaration order ----


def test_time_zero_ties_follow_graph_nodes_declaration_order() -> None:
    """Two independent roots F, E both feeding G; F declared before E."""
    graph = CompositionGraph(
        nodes=(node("F"), node("E"), node("G")),
        connections=(
            connection("F", "G", source_port_name="o1", target_port_name="i1"),
            connection("E", "G", source_port_name="o2", target_port_name="i2"),
        ),
    )
    result = plan(graph)
    ids = [step.node_id for step in result.steps]
    assert ids == ["F", "E", "G"]


def test_time_zero_ties_follow_reversed_graph_nodes_declaration_order() -> None:
    """Same shape, E declared before F: tie-break must follow suit,
    not fall back to id sort or any other implicit rule."""
    graph = CompositionGraph(
        nodes=(node("E"), node("F"), node("G")),
        connections=(
            connection("F", "G", source_port_name="o1", target_port_name="i1"),
            connection("E", "G", source_port_name="o2", target_port_name="i2"),
        ),
    )
    result = plan(graph)
    ids = [step.node_id for step in result.steps]
    assert ids == ["E", "F", "G"]


def test_ready_node_tie_break_uses_graph_node_declaration_order() -> None:
    """Regression guard for 13B.3 finding ADV-01: a LIFO-shaped queue
    (matching CompositionGraph._has_cycle()'s discipline) would visit
    A, C, B, D for this exact diamond - proven by direct construction
    during the adversarial review. FIFO must visit A, B, C, D."""
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    result = plan(graph)
    assert [step.node_id for step in result.steps] == ["A", "B", "C", "D"]


# --- E11b: mid-traversal tie-break follows connection discovery order ---


def test_mid_traversal_ties_follow_connection_declaration_order() -> None:
    """Regression guard for 13B.5 finding ADV-04: B and C both become
    ready only after A is processed. Their relative plan order must
    follow the order A->B/A->C were declared in graph.connections, NOT
    graph.nodes' declaration order."""
    graph_b_first = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    graph_c_first = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        connections=(
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("B", "D", source_port_name="o3", target_port_name="i3"),
            connection("C", "D", source_port_name="o4", target_port_name="i4"),
        ),
    )
    assert [s.node_id for s in plan(graph_b_first).steps] == ["A", "B", "C", "D"]
    assert [s.node_id for s in plan(graph_c_first).steps] == ["A", "C", "B", "D"]


def test_mid_traversal_tie_break_is_independent_of_graph_nodes_order() -> None:
    """Swapping B/C's position in graph.nodes must NOT change their
    relative plan order when both become ready only after A - proving
    the mid-traversal rule is genuinely connections-based, not
    accidentally still graph.nodes-based."""
    connections = (
        connection("A", "B", source_port_name="o1", target_port_name="i1"),
        connection("A", "C", source_port_name="o2", target_port_name="i2"),
        connection("B", "D", source_port_name="o3", target_port_name="i3"),
        connection("C", "D", source_port_name="o4", target_port_name="i4"),
    )
    graph_bc = CompositionGraph(
        nodes=(node("A"), node("B"), node("C"), node("D")), connections=connections
    )
    graph_cb = CompositionGraph(
        nodes=(node("A"), node("C"), node("B"), node("D")), connections=connections
    )
    assert [s.node_id for s in plan(graph_bc).steps] == ["A", "B", "C", "D"]
    assert [s.node_id for s in plan(graph_cb).steps] == ["A", "B", "C", "D"]


# --- E6: determinism ------------------------------------------------------


def test_repeated_planning_is_deterministic() -> None:
    graph = CompositionGraph(
        nodes=(node("A"), node("B"), node("C")),
        connections=(
            connection("A", "B", source_port_name="o1", target_port_name="i1"),
            connection("A", "C", source_port_name="o2", target_port_name="i2"),
        ),
    )
    assert plan(graph) == plan(graph)


def test_equal_graphs_produce_equal_plans() -> None:
    def build() -> CompositionGraph:
        return CompositionGraph(
            nodes=(node("A"), node("B")),
            connections=(connection("A", "B"),),
        )

    assert plan(build()) == plan(build())


# --- Value equality --------------------------------------------------------


def test_plans_with_different_steps_are_not_equal() -> None:
    graph1 = CompositionGraph(nodes=(node("A"), node("B")), connections=(connection("A", "B"),))
    graph2 = CompositionGraph(
        nodes=(node("A"), node("B"), node("C")),
        connections=(connection("A", "B"),),
    )
    assert plan(graph1) != plan(graph2)


# --- Immutability -----------------------------------------------------------


def test_execution_step_is_immutable() -> None:
    step = ExecutionStep(node_id="A", dependencies=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.node_id = "other"  # type: ignore[misc]


def test_execution_plan_is_immutable() -> None:
    result = ExecutionPlan(steps=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.steps = ()  # type: ignore[misc]


def test_dependencies_is_a_tuple() -> None:
    graph = CompositionGraph(nodes=(node("A"), node("B")), connections=(connection("A", "B"),))
    result = plan(graph)
    for step in result.steps:
        assert isinstance(step.dependencies, tuple)


def test_steps_is_a_tuple() -> None:
    graph = CompositionGraph(nodes=(node("A"),), connections=())
    assert isinstance(plan(graph).steps, tuple)


# --- Plan does not retain the source graph ----------------------------------


def test_execution_plan_has_no_graph_field() -> None:
    field_names = {field.name for field in dataclasses.fields(ExecutionPlan)}
    assert field_names == {"steps"}


def test_execution_step_has_no_component_or_node_field() -> None:
    field_names = {field.name for field in dataclasses.fields(ExecutionStep)}
    assert field_names == {"node_id", "dependencies"}


def test_plan_does_not_change_when_source_graph_changes_after() -> None:
    graph1 = CompositionGraph(nodes=(node("A"),), connections=())
    plan1 = plan(graph1)
    graph2 = graph1.add_node(node("B"))
    assert plan1 == plan(graph1)
    assert graph1 != graph2


# --- No component execution --------------------------------------------------


def test_planning_never_executes_components() -> None:
    exploding_node = node("exploder", ExplodingComponent())
    graph = CompositionGraph(nodes=(exploding_node,), connections=())
    result = plan(graph)
    assert result.steps == (ExecutionStep(node_id="exploder", dependencies=()),)


def test_planning_never_executes_components_in_a_chain() -> None:
    graph = CompositionGraph(
        nodes=(node("A", ExplodingComponent()), node("B", ExplodingComponent())),
        connections=(connection("A", "B"),),
    )
    result = plan(graph)
    assert [s.node_id for s in result.steps] == ["A", "B"]


# --- Provider independence / import boundary ---------------------------------


def test_execution_plan_module_has_no_provider_dependencies() -> None:
    import ast
    import inspect

    import ragtorch.core.execution_plan as execution_plan_module

    source = inspect.getsource(execution_plan_module)
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for import_node in ast.walk(tree):
        if isinstance(import_node, ast.Import):
            imported_modules.update(alias.name for alias in import_node.names)
        elif isinstance(import_node, ast.ImportFrom) and import_node.module:
            imported_modules.add(import_node.module)

    forbidden = ("openai", "anthropic", "transformers", "torch", "langchain", "llama")
    for module_name in imported_modules:
        top_level = module_name.split(".")[0].lower()
        assert top_level not in forbidden, f"unexpected import: {module_name}"


def test_execution_plan_module_does_not_import_execution_engine() -> None:
    import ast
    import inspect

    import ragtorch.core.execution_plan as execution_plan_module

    source = inspect.getsource(execution_plan_module)
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for import_node in ast.walk(tree):
        if isinstance(import_node, ast.Import):
            imported_modules.update(alias.name for alias in import_node.names)
        elif isinstance(import_node, ast.ImportFrom) and import_node.module:
            imported_modules.add(import_node.module)

    assert "ragtorch.core.engine" not in imported_modules
    assert not any(m.endswith(".engine") for m in imported_modules)


def test_execution_plan_module_does_not_use_annotation_evaluation() -> None:
    import inspect

    import ragtorch.core.execution_plan as execution_plan_module

    source = inspect.getsource(execution_plan_module)
    forbidden = ("get_type_hints", "eval(", "exec(")
    for expression in forbidden:
        assert expression not in source


def test_execution_plan_does_not_implement_iteration_protocol() -> None:
    """ADR-017: ExecutionPlan does not implement __iter__/__len__/
    __getitem__ in this version - use plan.steps directly."""
    result = ExecutionPlan(steps=())
    assert not hasattr(result, "__iter__") or not callable(getattr(type(result), "__iter__", None))
    assert not callable(getattr(type(result), "__len__", None))
    assert not callable(getattr(type(result), "__getitem__", None))
