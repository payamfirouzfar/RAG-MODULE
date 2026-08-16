"""Unit tests for the architecture snapshot (ADR-012)."""

from __future__ import annotations

import dataclasses

import pytest

from ragtorch.core.inspection import (
    ArchitectureChild,
    ArchitectureNode,
    ArchitectureSnapshot,
    snapshot,
)
from ragtorch.core.module import Module


class Double(Module):
    def forward(self, input):
        return input


class Parent(Module):
    def __init__(self):
        super().__init__()
        self.child_a = Double()
        self.child_b = Double()

    def forward(self, input):
        return input


class Grandparent(Module):
    def __init__(self):
        super().__init__()
        self.parent = Parent()

    def forward(self, input):
        return input


# -- construction ---------------------------------------------------


def test_architecture_node_is_constructed():
    node = ArchitectureNode(id="root", name="root", component_type="Root")
    assert node.id == "root"
    assert node.name == "root"
    assert node.component_type == "Root"


def test_architecture_node_defaults_to_empty_ports():
    node = ArchitectureNode(id="root", name="root", component_type="Root")
    assert node.input_ports == ()
    assert node.output_ports == ()


def test_architecture_child_is_constructed():
    child = ArchitectureChild(parent_id="root", child_id="root.child")
    assert child.parent_id == "root"
    assert child.child_id == "root.child"


def test_architecture_snapshot_is_constructed():
    node = ArchitectureNode(id="root", name="root", component_type="Root")
    snap = ArchitectureSnapshot(nodes=(node,), children=())
    assert snap.nodes == (node,)
    assert snap.children == ()


# -- immutability ------------------------------------------------------


def test_architecture_node_is_immutable():
    node = ArchitectureNode(id="root", name="root", component_type="Root")
    with pytest.raises(dataclasses.FrozenInstanceError):
        node.name = "other"  # type: ignore[misc]


def test_architecture_child_is_immutable():
    child = ArchitectureChild(parent_id="root", child_id="root.child")
    with pytest.raises(dataclasses.FrozenInstanceError):
        child.parent_id = "other"  # type: ignore[misc]


def test_architecture_snapshot_is_immutable():
    snap = ArchitectureSnapshot(nodes=(), children=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.nodes = ()  # type: ignore[misc]


# -- snapshot correctness -----------------------------------------------


def test_snapshot_contains_root_only_for_leaf_module():
    d = Double()
    snap = snapshot(d)
    assert len(snap.nodes) == 1
    assert snap.nodes[0].id == "Double"
    assert snap.nodes[0].name == "Double"
    assert snap.nodes[0].component_type == "Double"
    assert snap.children == ()


def test_snapshot_contains_nested_modules():
    p = Parent()
    snap = snapshot(p)
    ids = {n.id for n in snap.nodes}
    assert ids == {"Parent", "child_a", "child_b"}


def test_snapshot_uses_named_module_paths():
    g = Grandparent()
    snap = snapshot(g)
    ids = {n.id for n in snap.nodes}
    assert ids == {"Grandparent", "parent", "parent.child_a", "parent.child_b"}
    # exactly matches named_modules()'s own output
    assert ids == {path for path, _ in g.named_modules()}


def test_snapshot_contains_tree_children():
    p = Parent()
    snap = snapshot(p)
    pairs = {(c.parent_id, c.child_id) for c in snap.children}
    assert pairs == {("Parent", "child_a"), ("Parent", "child_b")}


def test_snapshot_nested_children_relationships():
    g = Grandparent()
    snap = snapshot(g)
    pairs = {(c.parent_id, c.child_id) for c in snap.children}
    assert pairs == {
        ("Grandparent", "parent"),
        ("parent", "parent.child_a"),
        ("parent", "parent.child_b"),
    }


def test_snapshot_does_not_infer_data_flow_edges():
    """Only parent->child tree containment appears - never sibling-to-
    sibling relationships, which would imply data flow this framework
    does not track (see ADR-012 Non-goals)."""
    p = Parent()
    snap = snapshot(p)
    pairs = {(c.parent_id, c.child_id) for c in snap.children}
    assert ("child_a", "child_b") not in pairs
    assert ("child_b", "child_a") not in pairs


# -- determinism ---------------------------------------------------------


def test_snapshot_is_deterministic():
    snapshot_a = snapshot(Parent())
    snapshot_b = snapshot(Parent())
    assert snapshot_a == snapshot_b


def test_snapshot_node_ordering_is_deterministic():
    ids_a = [n.id for n in snapshot(Grandparent()).nodes]
    ids_b = [n.id for n in snapshot(Grandparent()).nodes]
    assert ids_a == ids_b


# -- Module.snapshot() convenience method ---------------------------------


def test_module_snapshot_method_matches_free_function():
    p = Parent()
    assert p.snapshot() == snapshot(p)


# -- no execution ----------------------------------------------------------


class ExplodingComponent(Module):
    def forward(self, input):
        raise AssertionError("snapshot() must never execute a component")

    def __call__(self, input, *, context=None):
        raise AssertionError("snapshot() must never execute a component")


def test_snapshot_does_not_execute_components():
    exploding = ExplodingComponent()
    snap = snapshot(exploding)  # must not raise
    assert snap.nodes[0].component_type == "ExplodingComponent"


# -- security: no arbitrary instance state -----------------------------------


class SecretModule(Module):
    def __init__(self):
        super().__init__()
        self.api_key = "SUPER_SECRET_VALUE"
        self.password = "SUPER_SECRET_PASSWORD"

    def forward(self, input):
        return input


def test_snapshot_does_not_expose_arbitrary_instance_state():
    secret = SecretModule()
    snap = snapshot(secret)
    rendered = repr(snap)
    assert "SUPER_SECRET_VALUE" not in rendered
    assert "SUPER_SECRET_PASSWORD" not in rendered
    assert "api_key" not in rendered
    assert "password" not in rendered


# -- provider independence -----------------------------------------------


def test_inspection_module_has_no_provider_dependencies():
    """AST-based import check, reusing the Step 7 pattern: a naive
    substring scan would false-positive on "torch" being contained in
    "ragtorch" (see test_ports.py's equivalent test and its docstring)."""
    import ast
    import inspect as std_inspect

    import ragtorch.core.inspection as inspection_module

    source = std_inspect.getsource(inspection_module)
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


def test_inspection_module_does_not_use_annotation_evaluation():
    """No get_type_hints()/eval()/exec() - snapshot() never reflects
    over arbitrary annotations, matching the ADR-011 precedent."""
    import inspect as std_inspect

    import ragtorch.core.inspection as inspection_module

    source = std_inspect.getsource(inspection_module)
    forbidden = ("get_type_hints", "eval(", "exec(")
    for expression in forbidden:
        assert expression not in source
