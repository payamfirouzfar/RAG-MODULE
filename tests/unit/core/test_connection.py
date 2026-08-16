"""Unit tests for Connection (ADR-015)."""

from __future__ import annotations

import pytest

from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, check_connection


def make_connection(
    *,
    source_node_id: str = "retriever",
    source_port: OutputPort | None = None,
    target_node_id: str = "reranker",
    target_port: InputPort | None = None,
) -> Connection:
    return Connection(
        source_node_id=source_node_id,
        source_port=source_port or OutputPort(name="documents", type=list),
        target_node_id=target_node_id,
        target_port=target_port or InputPort(name="documents", type=list),
    )


def test_connection_constructs_for_compatible_ports() -> None:
    connection = make_connection()
    assert connection.source_node_id == "retriever"
    assert connection.target_node_id == "reranker"


def test_connection_accepts_subtype_compatible_ports() -> None:
    class Document:
        pass

    class DenseDocument(Document):
        pass

    connection = Connection(
        source_node_id="retriever",
        source_port=OutputPort(name="document", type=DenseDocument),
        target_node_id="reranker",
        target_port=InputPort(name="document", type=Document),
    )
    assert connection.target_node_id == "reranker"


def test_connection_rejects_incompatible_ports() -> None:
    with pytest.raises(ValidationError):
        Connection(
            source_node_id="retriever",
            source_port=OutputPort(name="documents", type=list),
            target_node_id="generator",
            target_port=InputPort(name="prompt", type=str),
        )


def test_connection_rejects_input_port_as_source() -> None:
    with pytest.raises(ValidationError, match="source_port"):
        Connection(
            source_node_id="retriever",
            source_port=InputPort(name="documents", type=list),  # type: ignore[arg-type]
            target_node_id="reranker",
            target_port=InputPort(name="documents", type=list),
        )


def test_connection_rejects_output_port_as_target() -> None:
    with pytest.raises(ValidationError, match="target_port"):
        Connection(
            source_node_id="retriever",
            source_port=OutputPort(name="documents", type=list),
            target_node_id="reranker",
            target_port=OutputPort(name="documents", type=list),  # type: ignore[arg-type]
        )


def test_connection_rejects_empty_source_node_id() -> None:
    with pytest.raises(ValidationError, match="source_node_id"):
        Connection(
            source_node_id="",
            source_port=OutputPort(name="documents", type=list),
            target_node_id="reranker",
            target_port=InputPort(name="documents", type=list),
        )


def test_connection_rejects_empty_target_node_id() -> None:
    with pytest.raises(ValidationError, match="target_node_id"):
        Connection(
            source_node_id="retriever",
            source_port=OutputPort(name="documents", type=list),
            target_node_id="",
            target_port=InputPort(name="documents", type=list),
        )


def test_connection_is_immutable() -> None:
    connection = make_connection()
    with pytest.raises(AttributeError):
        connection.source_node_id = "other"  # type: ignore[misc]


def test_equal_connections_have_value_equality() -> None:
    first = make_connection()
    second = make_connection()
    assert first == second


def test_different_target_node_makes_connections_unequal() -> None:
    first = make_connection(target_node_id="reranker")
    second = make_connection(target_node_id="generator")
    assert first != second


def test_connection_is_hashable() -> None:
    connection = make_connection()
    assert hash(connection) == hash(connection)
    assert {connection} == {connection}


def test_equal_connections_hash_equally() -> None:
    first = make_connection()
    second = make_connection()
    assert hash(first) == hash(second)


def test_multiple_connections_may_share_source() -> None:
    """Connection places no fan-out constraint - cardinality belongs to
    a future collection/Block contract, not this element type."""
    first = make_connection(target_node_id="reranker_a")
    second = make_connection(target_node_id="reranker_b")
    assert first.source_node_id == second.source_node_id
    assert first != second


def test_multiple_connections_may_share_target() -> None:
    """Same for fan-in: no constraint is implemented here."""
    first = make_connection(source_node_id="retriever_a")
    second = make_connection(source_node_id="retriever_b")
    assert first.target_node_id == second.target_node_id
    assert first != second


def test_connection_delegates_to_check_connection_not_duplicate_logic() -> None:
    output = OutputPort(name="documents", type=str)
    input_port = InputPort(name="prompt", type=int)

    with pytest.raises(ValidationError) as connection_exc:
        Connection(
            source_node_id="retriever",
            source_port=output,
            target_node_id="generator",
            target_port=input_port,
        )

    with pytest.raises(ValidationError) as direct_exc:
        check_connection(output, input_port)

    assert str(connection_exc.value) == str(direct_exc.value)


def test_connection_module_has_no_provider_dependencies() -> None:
    """Checks actual import statements, not a naive substring scan -
    "torch" is itself a substring of "ragtorch"."""
    import ast
    import inspect

    import ragtorch.core.connection as connection_module

    source = inspect.getsource(connection_module)
    tree = ast.parse(source)
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)

    forbidden = ("openai", "anthropic", "transformers", "torch", "langchain", "llama")
    for module_name in imported_modules:
        top_level = module_name.split(".")[0].lower()
        assert top_level not in forbidden, f"unexpected import: {module_name}"


def test_connection_module_does_not_use_annotation_evaluation() -> None:
    import inspect

    import ragtorch.core.connection as connection_module

    source = inspect.getsource(connection_module)
    forbidden = ("get_type_hints", "eval(", "exec(")
    for expression in forbidden:
        assert expression not in source
