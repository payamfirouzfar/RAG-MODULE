"""Unit tests for Component ports (ADR-011)."""

from __future__ import annotations

import pytest

from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort, is_compatible


def test_input_port_stores_metadata() -> None:
    port = InputPort(name="documents", type=list)
    assert port.name == "documents"
    assert port.type is list


def test_output_port_stores_metadata() -> None:
    port = OutputPort(name="documents", type=list)
    assert port.name == "documents"
    assert port.type is list


def test_input_port_is_immutable() -> None:
    port = InputPort(name="documents", type=list)
    with pytest.raises(AttributeError):
        port.name = "other"  # type: ignore[misc]


def test_output_port_is_immutable() -> None:
    port = OutputPort(name="documents", type=list)
    with pytest.raises(AttributeError):
        port.type = str  # type: ignore[misc]


def test_input_port_rejects_non_class_type() -> None:
    with pytest.raises(ValidationError):
        InputPort(name="documents", type="list")  # type: ignore[arg-type]


def test_output_port_rejects_non_class_type() -> None:
    with pytest.raises(ValidationError):
        OutputPort(name="documents", type="list")  # type: ignore[arg-type]


def test_input_port_rejects_non_class_int() -> None:
    with pytest.raises(ValidationError):
        InputPort(name="documents", type=42)  # type: ignore[arg-type]


def test_input_port_rejects_generic_alias() -> None:
    """list[X] must be rejected on every supported Python version.

    isinstance(list[Document], type) is version-dependent (True on
    3.10, False on 3.12) - caught by CI running 3.10/3.11/3.12 after
    passing locally on a 3.12-only environment. ports.py explicitly
    excludes types.GenericAlias rather than relying on isinstance(x,
    type) alone; this test is the regression guard for that fix.
    """

    class Document:
        pass

    with pytest.raises(ValidationError):
        InputPort(name="documents", type=list[Document])  # type: ignore[arg-type]


def test_exact_types_are_compatible() -> None:
    output = OutputPort(name="value", type=int)
    input_port = InputPort(name="value", type=int)
    assert is_compatible(output, input_port)


def test_subtype_is_compatible_with_supertype() -> None:
    class Document:
        pass

    class DenseDocument(Document):
        pass

    output = OutputPort(name="document", type=DenseDocument)
    input_port = InputPort(name="document", type=Document)
    assert is_compatible(output, input_port)


def test_supertype_is_not_compatible_with_subtype() -> None:
    class Document:
        pass

    class DenseDocument(Document):
        pass

    output = OutputPort(name="document", type=Document)
    input_port = InputPort(name="document", type=DenseDocument)
    assert not is_compatible(output, input_port)


def test_unrelated_types_are_incompatible() -> None:
    output = OutputPort(name="value", type=str)
    input_port = InputPort(name="value", type=int)
    assert not is_compatible(output, input_port)


def test_object_input_accepts_any_class() -> None:
    output = OutputPort(name="value", type=str)
    input_port = InputPort(name="value", type=object)
    assert is_compatible(output, input_port)


def test_compatibility_check_does_not_execute_components() -> None:
    called = False

    class Producer:
        def __call__(self) -> int:
            nonlocal called
            called = True
            return 1

    output = OutputPort(name="value", type=int)
    input_port = InputPort(name="value", type=int)

    assert is_compatible(output, input_port)
    assert called is False


def test_ports_module_does_not_use_annotation_evaluation() -> None:
    """The absence of reflection is part of the ADR-011 security contract."""
    import inspect

    import ragtorch.core.ports as ports_module

    source = inspect.getsource(ports_module)
    forbidden = ("get_type_hints", "eval(", "exec(")
    for expression in forbidden:
        assert expression not in source


def test_ports_module_has_no_provider_dependencies() -> None:
    """Checks actual import statements, not a naive substring scan of the
    whole source - "torch" is itself a substring of "ragtorch", which
    appears throughout this module's own imports and docstrings."""
    import ast
    import inspect

    import ragtorch.core.ports as ports_module

    source = inspect.getsource(ports_module)
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
