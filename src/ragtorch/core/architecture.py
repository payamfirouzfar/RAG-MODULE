"""Architecture snapshot validation: is an ArchitectureSnapshot a
well-formed, non-empty rooted tree?

Validation is a separate concern from execution and from snapshot
construction (ADR-013): it operates only on already-built
ArchitectureSnapshot data, is read-only, and never touches a live
Module, executes anything, or reflects over arbitrary object state.
See ADR-013 for the full ten-rule contract and why each check exists
in this specific order.
"""

from __future__ import annotations

from ragtorch.core.errors import ValidationError
from ragtorch.core.inspection import ArchitectureSnapshot


def validate_snapshot(snapshot: ArchitectureSnapshot) -> None:
    """Raise ValidationError if ``snapshot`` is not a well-formed,
    non-empty rooted tree. Returns None on success.

    Checks run in a fixed order (ADR-013 Algorithm) so a caller always
    learns the first real structural problem, not a downstream symptom
    of it: empty -> duplicate ids -> dangling references ->
    self-containment -> multiple parents -> root count -> reachability.
    """
    nodes = snapshot.nodes
    children = snapshot.children

    if not nodes:
        raise ValidationError("Architecture snapshot is empty; a valid architecture has a root.")

    nodes_by_id: dict[str, object] = {}
    for node in nodes:
        if node.id in nodes_by_id:
            raise ValidationError(f"Duplicate architecture node id: {node.id!r}")
        nodes_by_id[node.id] = node

    for child in children:
        if child.parent_id not in nodes_by_id:
            raise ValidationError(
                f"Dangling architecture child reference: parent {child.parent_id!r} does not exist."
            )
        if child.child_id not in nodes_by_id:
            raise ValidationError(
                f"Dangling architecture child reference: "
                f"{child.parent_id!r} -> {child.child_id!r} does not exist."
            )
        if child.parent_id == child.child_id:
            raise ValidationError(f"Architecture node cannot contain itself: {child.parent_id!r}")

    parent_by_child: dict[str, str] = {}
    for child in children:
        if child.child_id in parent_by_child:
            raise ValidationError(
                f"Architecture node {child.child_id!r} has more than one parent "
                f"(at least {parent_by_child[child.child_id]!r} and {child.parent_id!r}); "
                f"expected at most one."
            )
        parent_by_child[child.child_id] = child.parent_id

    roots = [node_id for node_id in nodes_by_id if node_id not in parent_by_child]
    if len(roots) != 1:
        raise ValidationError(
            f"Architecture snapshot must contain exactly one root; found {len(roots)}: "
            f"{sorted(roots)}"
        )
    root_id = roots[0]

    children_by_parent: dict[str, list[str]] = {}
    for child in children:
        children_by_parent.setdefault(child.parent_id, []).append(child.child_id)

    reachable: set[str] = set()
    stack = [root_id]
    while stack:
        current = stack.pop()
        if current in reachable:
            continue
        reachable.add(current)
        stack.extend(children_by_parent.get(current, []))

    unreachable = set(nodes_by_id) - reachable
    if unreachable:
        raise ValidationError(
            f"Architecture snapshot contains unreachable nodes: {sorted(unreachable)}"
        )
