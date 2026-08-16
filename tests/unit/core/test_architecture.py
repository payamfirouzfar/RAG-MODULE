"""Unit tests for architecture snapshot validation (ADR-013)."""

from __future__ import annotations

import pytest

from ragtorch.core.architecture import validate_snapshot
from ragtorch.core.errors import ValidationError
from ragtorch.core.inspection import ArchitectureChild, ArchitectureNode, ArchitectureSnapshot


def node(node_id: str) -> ArchitectureNode:
    return ArchitectureNode(id=node_id, name=node_id, component_type="X")


def child(parent_id: str, child_id: str) -> ArchitectureChild:
    return ArchitectureChild(parent_id=parent_id, child_id=child_id)


# -- valid cases -----------------------------------------------------------


def test_one_node_tree_is_valid():
    snap = ArchitectureSnapshot(nodes=(node("A"),), children=())
    assert validate_snapshot(snap) is None


def test_two_node_tree_is_valid():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("B")), children=(child("A", "B"),))
    assert validate_snapshot(snap) is None


def test_deep_tree_is_valid():
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        children=(child("A", "B"), child("B", "C"), child("C", "D")),
    )
    assert validate_snapshot(snap) is None


def test_branching_tree_is_valid():
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        children=(child("A", "B"), child("A", "C"), child("A", "D")),
    )
    assert validate_snapshot(snap) is None


# -- invalid cases, one violation each --------------------------------------


def test_empty_snapshot_is_invalid():
    snap = ArchitectureSnapshot(nodes=(), children=())
    with pytest.raises(ValidationError, match="empty"):
        validate_snapshot(snap)


def test_duplicate_node_id_is_invalid():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("A")), children=())
    with pytest.raises(ValidationError, match="Duplicate architecture node id: 'A'"):
        validate_snapshot(snap)


def test_dangling_child_reference_is_invalid():
    snap = ArchitectureSnapshot(nodes=(node("A"),), children=(child("A", "X"),))
    with pytest.raises(ValidationError, match="Dangling"):
        validate_snapshot(snap)


def test_dangling_parent_reference_is_invalid():
    snap = ArchitectureSnapshot(nodes=(node("A"),), children=(child("X", "A"),))
    with pytest.raises(ValidationError, match="Dangling"):
        validate_snapshot(snap)


def test_self_containment_is_invalid():
    snap = ArchitectureSnapshot(nodes=(node("A"),), children=(child("A", "A"),))
    with pytest.raises(ValidationError, match="cannot contain itself"):
        validate_snapshot(snap)


def test_diamond_multiple_parents_is_invalid():
    """A->B, A->C, B->D, C->D: exactly one root (A), zero duplicate IDs,
    but D has two parents - proves 'one root' alone is insufficient to
    prove a tree (ADR-013 Correction #2)."""
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        children=(child("A", "B"), child("A", "C"), child("B", "D"), child("C", "D")),
    )
    with pytest.raises(ValidationError, match="more than one parent"):
        validate_snapshot(snap)


def test_cycle_produces_zero_roots_is_invalid():
    """A->B->C->A: zero duplicate IDs, every node has exactly one
    parent, yet zero nodes have zero incoming edges."""
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C")),
        children=(child("A", "B"), child("B", "C"), child("C", "A")),
    )
    with pytest.raises(ValidationError, match="exactly one root"):
        validate_snapshot(snap)


def test_multiple_roots_is_invalid():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("B")), children=())
    with pytest.raises(ValidationError, match="exactly one root"):
        validate_snapshot(snap)


def test_disconnected_node_is_invalid():
    """A->B is a valid subtree; C has no relationship to anything, so
    it also has zero incoming edges - caught as a second root."""
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C")), children=(child("A", "B"),)
    )
    with pytest.raises(ValidationError, match="exactly one root"):
        validate_snapshot(snap)


def test_disconnected_cycle_is_invalid():
    """A->B is a valid subtree (A is the sole root); C->D->C is a
    disjoint mutual cycle where both C and D have incoming edges, so
    root-counting alone does not catch it - reachability does."""
    snap = ArchitectureSnapshot(
        nodes=(node("A"), node("B"), node("C"), node("D")),
        children=(child("A", "B"), child("C", "D"), child("D", "C")),
    )
    with pytest.raises(ValidationError, match="unreachable"):
        validate_snapshot(snap)


# -- read-only / determinism -------------------------------------------------


def test_validation_does_not_mutate_snapshot():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("B")), children=(child("A", "B"),))
    nodes_before = snap.nodes
    children_before = snap.children
    validate_snapshot(snap)
    assert snap.nodes is nodes_before
    assert snap.children is children_before


def test_validation_is_deterministic_on_success():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("B")), children=(child("A", "B"),))
    assert validate_snapshot(snap) is None
    assert validate_snapshot(snap) is None


def test_validation_is_deterministic_on_failure():
    snap = ArchitectureSnapshot(nodes=(node("A"), node("A")), children=())
    first_message = None
    for _ in range(2):
        with pytest.raises(ValidationError) as exc_info:
            validate_snapshot(snap)
        if first_message is None:
            first_message = str(exc_info.value)
        else:
            assert str(exc_info.value) == first_message


# -- security / provider independence ----------------------------------------


def test_architecture_module_has_no_provider_dependencies():
    """AST-based import check, reusing the Step 7/8 pattern: a naive
    substring scan would false-positive on "torch" being contained in
    "ragtorch"."""
    import ast
    import inspect as std_inspect

    import ragtorch.core.architecture as architecture_module

    source = std_inspect.getsource(architecture_module)
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


def test_architecture_module_does_not_use_annotation_evaluation():
    """No get_type_hints()/eval()/exec()/vars()/getattr reflection over
    arbitrary objects - validate_snapshot() only reads defined
    ArchitectureNode/ArchitectureChild fields."""
    import inspect as std_inspect

    import ragtorch.core.architecture as architecture_module

    source = std_inspect.getsource(architecture_module)
    forbidden = ("get_type_hints", "eval(", "exec(", "vars(")
    for expression in forbidden:
        assert expression not in source
