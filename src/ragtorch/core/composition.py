"""CompositionGraph: an immutable, validated collection of nodes and
directed data-flow Connections (ADR-016).

CompositionGraph answers the question Connection (Step 11) alone
cannot: given a set of nodes and a set of Connections between them, is
that collection a valid composition? "Valid" means: unique node ids,
every connection references a real node, no duplicate connections, at
most one incoming connection per input port (fan-in <= 1), unlimited
outgoing connections per output port (fan-out unrestricted), and no
directed cycle.

GraphNode.id is graph-local identity, unrelated to and not derived
from ArchitectureNode.id (ADR-012) -- the two identity systems are
deliberately independent so an unrelated Module-tree refactor never
silently breaks composition-graph identity.

CompositionGraph never executes a component: no operation defined here
ever calls a GraphNode's component.__call__. It also does not build,
consume, or integrate with ArchitectureSnapshot/validate_snapshot()
-- containment and data-flow composition remain independent concepts,
per ADR-012's own non-goal.

Deliberately out of scope: a Block type, execution planning/ordering,
serialization, observability, async, and a fan-in override mechanism.
See ADR-016 Non-goals for the full list and reasoning.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ragtorch.core.component import Component
from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError


@dataclass(frozen=True)
class GraphNode:
    """One component's identity and membership within a CompositionGraph.

    Deliberately minimal: id and component only. Ports remain external
    metadata (ADR-011 Non-goals) -- GraphNode does not gain
    input_ports/output_ports fields, since that information already
    lives on the OutputPort/InputPort instances a Connection references
    directly. GraphNode.component is accepted structurally-typed and
    unchecked (no isinstance(component, Component) here) -- ADR-010
    prohibits Component conformance checks on paths that run once per
    node in a potentially large composition.
    """

    id: str
    component: Component[object, object]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValidationError("GraphNode id must be a non-empty string.")


def _has_cycle(node_ids: tuple[str, ...], connections: tuple[Connection, ...]) -> bool:
    """Iterative Kahn's-algorithm cycle detection over (source_node_id,
    target_node_id) pairs.

    Deliberately iterative, not recursive DFS: a recursive
    implementation hits Python's default recursion limit on a long
    linear chain (a real failure caught by benchmarking a 1,000-node
    chain, not assumed safe from the algorithm's correctness alone).
    A graph is acyclic if and only if repeatedly removing all
    zero-in-degree nodes eventually removes every node.
    """
    edges: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for connection in connections:
        edges[connection.source_node_id].append(connection.target_node_id)
        in_degree[connection.target_node_id] += 1

    queue = [node_id for node_id in node_ids if in_degree[node_id] == 0]
    visited_count = 0
    while queue:
        current = queue.pop()
        visited_count += 1
        for neighbor in edges[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return visited_count != len(node_ids)


@dataclass(frozen=True)
class CompositionGraph:
    """An immutable, validated collection of GraphNodes and Connections.

    See ADR-016's canonical invariant list. Construction-time validated,
    in fixed order: unique node ids, every connection references an
    existing node, no duplicate connections, fan-in <= 1 per
    (target_node_id, target_port), acyclic. Connection directionality
    and port compatibility (ADR-015) are inherited for free -- every
    Connection instance already guarantees both, so they are not
    re-checked here.

    nodes/connections are ordered tuples: iteration order is
    deterministic and is preserved (append order for additions,
    relative order for removals) across every operation.
    """

    nodes: tuple[GraphNode, ...]
    connections: tuple[Connection, ...]

    def __post_init__(self) -> None:
        node_ids = tuple(node.id for node in self.nodes)
        seen_ids: set[str] = set()
        for node_id in node_ids:
            if node_id in seen_ids:
                raise ValidationError(f"Duplicate node id {node_id!r} in CompositionGraph.")
            seen_ids.add(node_id)

        for connection in self.connections:
            if connection.source_node_id not in seen_ids:
                raise ValidationError(
                    f"Connection references unknown source_node_id {connection.source_node_id!r}."
                )
            if connection.target_node_id not in seen_ids:
                raise ValidationError(
                    f"Connection references unknown target_node_id {connection.target_node_id!r}."
                )

        seen_connections: set[Connection] = set()
        for connection in self.connections:
            if connection in seen_connections:
                raise ValidationError(f"Duplicate connection {connection!r} in CompositionGraph.")
            seen_connections.add(connection)

        seen_targets: set[tuple[str, str]] = set()
        for connection in self.connections:
            target_key = (connection.target_node_id, connection.target_port.name)
            if target_key in seen_targets:
                raise ValidationError(
                    f"Input port {connection.target_port.name!r} on node "
                    f"{connection.target_node_id!r} already has an incoming connection "
                    "(fan-in is limited to one connection per input port)."
                )
            seen_targets.add(target_key)

        if _has_cycle(node_ids, self.connections):
            raise ValidationError("CompositionGraph must be acyclic.")

    def add_node(self, node: GraphNode) -> CompositionGraph:
        """Return a new CompositionGraph with node appended. Does not mutate self."""
        return replace(self, nodes=(*self.nodes, node))

    def add_connection(self, connection: Connection) -> CompositionGraph:
        """Return a new CompositionGraph with connection appended. Does not mutate self."""
        return replace(self, connections=(*self.connections, connection))

    def remove_node(self, node_id: str) -> CompositionGraph:
        """Return a new CompositionGraph without the node whose id is node_id.

        Raises ValidationError if any existing connection still
        references node_id -- the caller must remove the connection(s)
        first, so removal never silently produces a graph with a
        dangling connection.
        """
        for connection in self.connections:
            if connection.source_node_id == node_id or connection.target_node_id == node_id:
                raise ValidationError(
                    f"Cannot remove node {node_id!r}: still referenced by a connection."
                )
        return replace(self, nodes=tuple(node for node in self.nodes if node.id != node_id))

    def remove_connection(self, connection: Connection) -> CompositionGraph:
        """Return a new CompositionGraph without the given connection."""
        return replace(self, connections=tuple(c for c in self.connections if c != connection))
