"""Unit tests for CompositionGraph/GraphNode (ADR-016).

Organized around ADR-016's nine canonical invariants, not as an
independent collection of examples."""

from __future__ import annotations

import pytest

from ragtorch.core.component import Component
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


class ExplodingComponent:
    """Raises if ever called - proves CompositionGraph never executes it."""

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


# --- GraphNode -------------------------------------------------------------


def test_graph_node_stores_id_and_component() -> None:
    n = node("a")
    assert n.id == "a"
    assert isinstance(n.component, FakeComponent)


def test_graph_node_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        GraphNode(id="", component=FakeComponent())


def test_graph_node_is_immutable() -> None:
    n = node("a")
    with pytest.raises(AttributeError):
        n.id = "other"  # type: ignore[misc]


def test_graph_node_has_value_equality() -> None:
    component = FakeComponent()
    assert GraphNode(id="a", component=component) == GraphNode(id="a", component=component)


def test_graph_node_id_is_independent_of_architecture_path() -> None:
    """GraphNode.id is graph-local identity, not derived from or coupled
    to ArchitectureNode.id (ADR-012's dotted named_modules() path)."""
    n = GraphNode(id="totally-unrelated-string-not-a-module-path", component=FakeComponent())
    assert n.id == "totally-unrelated-string-not-a-module-path"


# --- Invariant 1: unique node ids -------------------------------------------


def test_construction_succeeds_with_unique_node_ids() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    assert len(graph.nodes) == 2


def test_construction_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValidationError):
        CompositionGraph(nodes=(node("a"), node("a")), connections=())


def test_empty_graph_is_valid() -> None:
    graph = CompositionGraph(nodes=(), connections=())
    assert graph.nodes == ()
    assert graph.connections == ()


# --- Invariant 2: referential integrity -------------------------------------


def test_construction_rejects_connection_with_unknown_source() -> None:
    with pytest.raises(ValidationError, match="source_node_id"):
        CompositionGraph(nodes=(node("b"),), connections=(connection("unknown", "b"),))


def test_construction_rejects_connection_with_unknown_target() -> None:
    with pytest.raises(ValidationError, match="target_node_id"):
        CompositionGraph(nodes=(node("a"),), connections=(connection("a", "unknown"),))


# --- Invariants 3-4: directionality/compatibility inherited from Connection


def test_incompatible_connection_cannot_be_constructed_to_add_to_graph() -> None:
    with pytest.raises(ValidationError):
        Connection(
            source_node_id="a",
            source_port=OutputPort(name="out", type=str),
            target_node_id="b",
            target_port=InputPort(name="in", type=int),
        )


# --- Invariant 5: no duplicate connections ----------------------------------


def test_construction_rejects_duplicate_connections() -> None:
    conn = connection("a", "b")
    with pytest.raises(ValidationError):
        CompositionGraph(nodes=(node("a"), node("b")), connections=(conn, conn))


# --- Invariant 6: fan-in <= 1 ------------------------------------------------


def test_construction_rejects_fan_in_to_same_target_port() -> None:
    conn_ab = connection("a", "c", source_port_name="out_a")
    conn_bc = connection("b", "c", source_port_name="out_b")
    with pytest.raises(ValidationError, match="fan-in"):
        CompositionGraph(nodes=(node("a"), node("b"), node("c")), connections=(conn_ab, conn_bc))


def test_construction_allows_different_target_ports_on_same_node() -> None:
    conn_a = connection("a", "c", source_port_name="out_a", target_port_name="in_a")
    conn_b = connection("b", "c", source_port_name="out_b", target_port_name="in_b")
    graph = CompositionGraph(nodes=(node("a"), node("b"), node("c")), connections=(conn_a, conn_b))
    assert len(graph.connections) == 2


# --- Invariant 7: fan-out unrestricted ---------------------------------------


def test_construction_allows_fan_out_from_same_source() -> None:
    conn_ab = connection("a", "b", target_port_name="in_b")
    conn_ac = connection("a", "c", target_port_name="in_c")
    graph = CompositionGraph(
        nodes=(node("a"), node("b"), node("c")), connections=(conn_ab, conn_ac)
    )
    assert len(graph.connections) == 2


# --- Invariant 8: acyclic -----------------------------------------------------


def test_construction_rejects_two_node_cycle() -> None:
    conn_ab = connection("a", "b")
    conn_ba = connection("b", "a")
    with pytest.raises(ValidationError, match="acyclic"):
        CompositionGraph(nodes=(node("a"), node("b")), connections=(conn_ab, conn_ba))


def test_construction_rejects_three_node_cycle() -> None:
    conn_ab = connection("a", "b")
    conn_bc = connection("b", "c")
    conn_ca = connection("c", "a")
    with pytest.raises(ValidationError, match="acyclic"):
        CompositionGraph(
            nodes=(node("a"), node("b"), node("c")), connections=(conn_ab, conn_bc, conn_ca)
        )


def test_construction_rejects_disconnected_cycle() -> None:
    """A valid A->B chain plus a disconnected C<->D cycle."""
    conn_ab = connection("a", "b")
    conn_cd = connection("c", "d")
    conn_dc = connection("d", "c")
    with pytest.raises(ValidationError, match="acyclic"):
        CompositionGraph(
            nodes=(node("a"), node("b"), node("c"), node("d")),
            connections=(conn_ab, conn_cd, conn_dc),
        )


def test_construction_accepts_valid_linear_chain() -> None:
    """A->B->C->D must not be over-rejected as a cycle."""
    conn_ab = connection("a", "b")
    conn_bc = connection("b", "c", source_port_name="out2", target_port_name="in2")
    conn_cd = connection("c", "d", source_port_name="out3", target_port_name="in3")
    graph = CompositionGraph(
        nodes=(node("a"), node("b"), node("c"), node("d")),
        connections=(conn_ab, conn_bc, conn_cd),
    )
    assert len(graph.connections) == 3


# --- Invariant 9: no dangling connections after removal ----------------------


def test_remove_node_rejects_if_referenced_by_connection() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b")), connections=(connection("a", "b"),))
    with pytest.raises(ValidationError):
        graph.remove_node("a")
    with pytest.raises(ValidationError):
        graph.remove_node("b")


def test_remove_node_succeeds_when_unreferenced() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    result = graph.remove_node("a")
    assert [n.id for n in result.nodes] == ["b"]


# --- Immutability / functional update semantics ------------------------------


def test_composition_graph_is_immutable() -> None:
    graph = CompositionGraph(nodes=(node("a"),), connections=())
    with pytest.raises(AttributeError):
        graph.nodes = ()  # type: ignore[misc]


def test_add_node_returns_new_graph_without_mutating_original() -> None:
    g0 = CompositionGraph(nodes=(), connections=())
    a = node("a")
    g1 = g0.add_node(a)
    assert g0.nodes == ()
    assert g1.nodes == (a,)
    assert g0 != g1


def test_add_connection_returns_new_graph_without_mutating_original() -> None:
    g1 = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    conn = connection("a", "b")
    g2 = g1.add_connection(conn)
    assert g1.connections == ()
    assert g2.connections == (conn,)
    assert g1 != g2


def test_chained_updates_preserve_each_intermediate_graph() -> None:
    a = node("a")
    b = node("b")
    conn = connection("a", "b")

    g0 = CompositionGraph(nodes=(), connections=())
    g1 = g0.add_node(a)
    g2 = g1.add_node(b)
    g3 = g2.add_connection(conn)

    assert g0.nodes == ()
    assert g1.nodes == (a,)
    assert g2.nodes == (a, b)
    assert g2.connections == ()
    assert g3.connections == (conn,)


def test_remove_connection_returns_graph_without_that_connection() -> None:
    conn = connection("a", "b")
    graph = CompositionGraph(nodes=(node("a"), node("b")), connections=(conn,))
    result = graph.remove_connection(conn)
    assert result.connections == ()
    assert graph.connections == (conn,)


# --- Determinism ---------------------------------------------------------------


def test_iteration_order_is_stable_across_repeated_access() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b"), node("c")), connections=())
    assert tuple(graph.nodes) == tuple(graph.nodes)


def test_equal_graphs_iterate_in_same_order() -> None:
    graph1 = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    graph2 = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    assert [n.id for n in graph1.nodes] == [n.id for n in graph2.nodes]


def test_add_node_appends_new_node_last() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b")), connections=())
    result = graph.add_node(node("c"))
    assert [n.id for n in result.nodes] == ["a", "b", "c"]


def test_remove_node_preserves_relative_order_of_remaining_nodes() -> None:
    graph = CompositionGraph(nodes=(node("a"), node("b"), node("c")), connections=())
    result = graph.remove_node("b")
    assert [n.id for n in result.nodes] == ["a", "c"]


# --- No component execution -----------------------------------------------------


def test_construction_never_executes_component() -> None:
    exploding_node = node("exploder", ExplodingComponent())
    graph = CompositionGraph(nodes=(exploding_node,), connections=())
    assert graph.nodes == (exploding_node,)


def test_graph_operations_never_execute_component() -> None:
    exploding_node = node("exploder", ExplodingComponent())
    graph = CompositionGraph(nodes=(node("a"),), connections=())
    graph = graph.add_node(exploding_node)
    graph = graph.add_connection(connection("a", "exploder"))
    graph = graph.remove_connection(connection("a", "exploder"))
    graph = graph.remove_node("exploder")
    assert True  # reaching here without AssertionError proves no execution occurred


# --- Provider independence -------------------------------------------------------


def test_composition_module_has_no_provider_dependencies() -> None:
    import ast
    import inspect

    import ragtorch.core.composition as composition_module

    source = inspect.getsource(composition_module)
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


def test_composition_module_does_not_use_annotation_evaluation() -> None:
    import inspect

    import ragtorch.core.composition as composition_module

    source = inspect.getsource(composition_module)
    forbidden = ("get_type_hints", "eval(", "exec(")
    for expression in forbidden:
        assert expression not in source
