"""Contract tests for Component (ADR-010).

These test the structural contract itself, not Module's internals:
Module must satisfy Component, an independent non-Module class must
also satisfy it (proving this is genuinely structural typing), and a
deliberately incomplete class must not satisfy it (proving the
protocol isn't accidentally permissive).
"""

from __future__ import annotations

import pytest

from ragtorch.core.component import Component
from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ExecutionError
from ragtorch.core.module import Module


class EchoModule(Module):
    def forward(self, input: str) -> str:
        return input


class FailingModule(Module):
    def forward(self, input: str) -> str:
        raise ValueError("boom")


class ExternalComponent:
    """Deliberately does not inherit from Module."""

    @property
    def name(self) -> str:
        return "ExternalComponent"

    @property
    def component_type(self) -> str:
        return "ExternalComponent"

    def __call__(self, input: str, *, context: ExecutionContext | None = None) -> str:
        return input


class IntToStringComponent:
    """A second independent implementation, with a different input/output
    type, proving the generic contract isn't tied to str."""

    @property
    def name(self) -> str:
        return "IntToString"

    @property
    def component_type(self) -> str:
        return "IntToString"

    def __call__(self, input: int, *, context: ExecutionContext | None = None) -> str:
        return str(input)


class IncompleteComponent:
    """Missing component_type and __call__ — must NOT satisfy Component."""

    @property
    def name(self) -> str:
        return "incomplete"


def test_module_subclass_satisfies_component_protocol() -> None:
    module = EchoModule()
    assert isinstance(module, Component)


def test_component_name_matches_module_name() -> None:
    module = EchoModule()
    assert module.name == "EchoModule"


def test_component_type_is_class_name() -> None:
    module = EchoModule()
    assert module.component_type == "EchoModule"


def test_non_module_object_can_satisfy_component_protocol() -> None:
    component = ExternalComponent()
    assert not isinstance(component, Module)
    assert isinstance(component, Component)


def test_incomplete_object_does_not_satisfy_component_protocol() -> None:
    incomplete = IncompleteComponent()
    assert not isinstance(incomplete, Component)


def test_component_module_still_executes() -> None:
    module = EchoModule()
    assert module("hello") == "hello"


def test_component_accepts_execution_context() -> None:
    module = EchoModule()
    context = ExecutionContext()
    assert module("hello", context=context) == "hello"


def test_external_component_executes_without_context() -> None:
    component = ExternalComponent()
    assert component("hello") == "hello"


def test_external_component_executes_with_context() -> None:
    component = ExternalComponent()
    context = ExecutionContext()
    assert component("hello", context=context) == "hello"


def test_component_protocol_supports_non_module_generic_component() -> None:
    component: Component[int, str] = IntToStringComponent()
    assert component(42) == "42"


def test_component_does_not_change_module_error_behavior() -> None:
    module = FailingModule()
    with pytest.raises(ExecutionError):
        module("input")
