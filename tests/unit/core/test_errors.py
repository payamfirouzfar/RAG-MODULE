from __future__ import annotations

from ragtorch.core.errors import (
    ConfigurationError,
    ExecutionError,
    ModuleError,
    RAGTorchError,
    RegistryError,
    ValidationError,
)


def test_all_errors_inherit_from_base():
    for cls in (
        ConfigurationError,
        ModuleError,
        ExecutionError,
        RegistryError,
        ValidationError,
    ):
        assert issubclass(cls, RAGTorchError)


def test_errors_are_catchable_via_base():
    try:
        raise ExecutionError("boom")
    except RAGTorchError as exc:
        assert str(exc) == "boom"
    else:
        raise AssertionError("expected RAGTorchError to catch ExecutionError")
