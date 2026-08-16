"""Canonical architecture snapshot: the single source of truth for
describing a Module tree's structure.

ArchitectureSnapshot exists so every future consumer that needs to
describe architecture (renderers, serializers, a future graph/composition
layer) walks the Module tree exactly once, through snapshot(), rather
than each independently re-implementing tree traversal. Module.inspect()
is migrated to consume this rather than walking _modules a second way.
See ADR-012 for the full design rationale, including why node identity
reuses named_modules()'s existing dotted paths (not id()/uuid), why
ArchitectureChild represents tree containment only (never a data-flow
edge), and why ports default to empty rather than being auto-discovered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ragtorch.core.ports import InputPort, OutputPort

if TYPE_CHECKING:
    from ragtorch.core.module import Module


@dataclass(frozen=True)
class ArchitectureNode:
    """One component's identity and type within a snapshot.

    ``input_ports``/``output_ports`` default to empty: snapshot() never
    auto-discovers ports from arbitrary Module attributes (no such
    convention exists — see ADR-012), so a node's ports are only ever
    non-empty when explicitly supplied to a future port-aware snapshot
    call.
    """

    id: str
    name: str
    component_type: str
    input_ports: tuple[InputPort, ...] = field(default_factory=tuple)
    output_ports: tuple[OutputPort, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ArchitectureChild:
    """A parent -> child tree containment relationship.

    Deliberately not named "edge": this represents Module registration/
    tree structure only, never a data-flow relationship ("this
    component's output feeds that component's input"). Data-flow edges
    are explicit future work once a real composition/graph contract
    defines what that means — see ADR-012 Non-goals.
    """

    parent_id: str
    child_id: str


@dataclass(frozen=True)
class ArchitectureSnapshot:
    """An immutable, deterministic description of a Module tree."""

    nodes: tuple[ArchitectureNode, ...]
    children: tuple[ArchitectureChild, ...]


def snapshot(module: Module) -> ArchitectureSnapshot:
    """Build an immutable snapshot of ``module``'s architecture.

    Walks module.named_modules() once to build every node (its dotted
    path is exactly what that API already produces — no path is
    reconstructed by hand, avoiding a subtle mismatch with
    named_modules()'s own prefix rules at the root level). A second,
    shallow pass over each node's named_children() builds parent/child
    pairs, using an id(child-object) -> dotted-path lookup collected
    during the first pass rather than calling named_modules() again.
    Never calls module(...) or any descendant's forward()/__call__;
    never reads instance __dict__ or vars() — only the existing
    name/component_type properties and the named_modules()/
    named_children() structure are read. See ADR-012 Security.
    """
    nodes: list[ArchitectureNode] = []
    path_by_module: dict[int, str] = {}
    for node_id, node in module.named_modules():
        path_by_module[id(node)] = node_id
        nodes.append(
            ArchitectureNode(id=node_id, name=node.name, component_type=node.component_type)
        )

    children = tuple(
        ArchitectureChild(parent_id=path_by_module[id(node)], child_id=path_by_module[id(child)])
        for node in (n for _, n in module.named_modules())
        for _child_name, child in node.named_children()
    )
    return ArchitectureSnapshot(nodes=tuple(nodes), children=children)
