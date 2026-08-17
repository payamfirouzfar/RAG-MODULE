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


# ---------------------------------------------------------------------------
# A16: Component conformance checks never occur on a hot execution path
# (ADR-010 hard rule). Automated enforcement, Step 24 -- previously a
# documented rule + code review only, with no regression protection.
# AST-based scan, reusing the established pattern from
# test_architecture_module_has_no_provider_dependencies() and its
# siblings (Steps 7-16): parse each hot-path file's actual source, walk
# for isinstance() calls whose second argument is the name `Component`,
# assert none exist. Scoped to this codebase's own hot-path files, not
# a general project-wide lint rule -- no evidence justifies the larger
# scope of a custom linter plugin (Step 24 design-space comparison).
# ---------------------------------------------------------------------------


def _isinstance_component_calls_in_source(source: str) -> list[int]:
    """Return the line numbers of every isinstance(_, Component) call
    (by any means of referencing the Component name, including a
    dotted/aliased attribute access) found in source."""
    import ast

    tree = ast.parse(source)
    violations: list[int] = []

    def references_component(node: ast.expr) -> bool:
        if isinstance(node, ast.Name):
            return node.id == "Component"
        if isinstance(node, ast.Attribute):
            return node.attr == "Component"
        return False

    for call_node in ast.walk(tree):
        if (
            isinstance(call_node, ast.Call)
            and isinstance(call_node.func, ast.Name)
            and call_node.func.id == "isinstance"
            and len(call_node.args) == 2
            and references_component(call_node.args[1])
        ):
            violations.append(call_node.lineno)

    return violations


def _hot_path_isinstance_component_calls(module) -> list[int]:
    """Return the line numbers of every isinstance(_, Component) call
    found in module's actual source."""
    import inspect as std_inspect

    return _isinstance_component_calls_in_source(std_inspect.getsource(module))


@pytest.mark.parametrize(
    "module_path",
    [
        "ragtorch.core.module",
        "ragtorch.core.engine",
        "ragtorch.core.sequential",
        "ragtorch.core.block",
    ],
)
def test_hot_path_never_checks_isinstance_component(module_path: str) -> None:
    import importlib

    module = importlib.import_module(module_path)
    violations = _hot_path_isinstance_component_calls(module)
    assert violations == [], (
        f"{module_path} contains isinstance(_, Component) call(s) at "
        f"line(s) {violations} -- forbidden on a hot execution path "
        f"per ADR-010's hard rule (A16)."
    )


def test_hot_path_enforcement_detector_actually_detects_a_violation() -> None:
    """Tests the test: confirms _isinstance_component_calls_in_source
    would actually catch a real violation, so a bug in the AST-walking
    logic itself can't silently make the four tests above pass for the
    wrong reason (always finding zero violations regardless of
    content)."""
    fake_source = (
        "from ragtorch.core.component import Component\n"
        "def f(x):\n"
        "    if isinstance(x, Component):\n"
        "        return True\n"
        "    return False\n"
    )

    violations = _isinstance_component_calls_in_source(fake_source)
    assert violations == [3]


def test_hot_path_enforcement_detector_ignores_unrelated_isinstance_calls() -> None:
    """Confirms the detector doesn't over-match: an isinstance() check
    against an unrelated type must not be flagged."""
    fake_source = "def f(x):\n    if isinstance(x, str):\n        return True\n"

    violations = _isinstance_component_calls_in_source(fake_source)
    assert violations == []
