"""ExecutionPlan: a deterministic topological ordering derived from a
CompositionGraph (ADR-017).

plan() answers the question CompositionGraph alone cannot: given a
valid composition, what is a deterministic, dependency-respecting
execution order? CompositionGraph (ADR-016) already guarantees
acyclicity, referential integrity, and no duplicate connections; plan()
trusts that guarantee rather than re-checking it -- the same
single-source-of-truth discipline is_compatible()/check_connection()/
Connection/CompositionGraph already established layer by layer.

Ordering uses Kahn's algorithm with an explicit FIFO ready queue
(collections.deque, popleft()/append()) -- deliberately NOT the LIFO
list.pop() shape CompositionGraph._has_cycle() uses for cycle
detection. The two functions answer different questions:
_has_cycle() only needs a yes/no answer and never exposes traversal
order; plan()'s output order is itself the public, observable
contract, so the queue discipline is part of that contract, not an
implementation detail free to vary. See ADR-017 "Ordering algorithm"
for the full reasoning, including the direct-construction proof that a
LIFO queue silently reverses ties relative to declared order.

Two distinct, both-deterministic tie-break rules apply when multiple
nodes become ready simultaneously:
  - Nodes ready at the start (in-degree zero before any node is
    processed) are enqueued in graph.nodes' own declaration order.
  - Nodes that become ready later are enqueued in the order their
    enabling Connection was encountered while scanning
    graph.connections during adjacency-list construction.

ExecutionPlan contains no runtime objects (no Component, no GraphNode,
no Connection, no ExecutionEngine/ExecutionContext reference) and does
not retain a reference to the CompositionGraph it was derived from --
deriving a plan is a one-way, pure transformation. plan() never calls
any node's component.__call__.

Deliberately out of scope: an executor, ExecutionEngine integration,
parallel/async execution, retries/timeouts/scheduling metadata,
serialization, and __iter__/__len__/__getitem__ on ExecutionPlan (use
plan.steps directly). See ADR-017 Non-goals for the full list.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ragtorch.core.composition import CompositionGraph


@dataclass(frozen=True)
class ExecutionStep:
    """One node's position within a plan: its identity and its direct
    dependencies, both by graph-local node id.

    dependencies contains only direct predecessors (nodes with a
    Connection whose target_node_id is this step's node_id) -- not the
    full transitive dependency set. A consumer that needs transitive
    dependencies derives them by walking the plan; ExecutionStep does
    not precompute or cache that separately.
    """

    node_id: str
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class ExecutionPlan:
    """A deterministic topological ordering of a CompositionGraph's nodes.

    steps[i].node_id names a GraphNode.id from the source graph; steps
    is ordered such that every dependency of steps[i] appears at some
    index j < i. Contains no Component instances, no callables, and no
    ExecutionEngine/ExecutionContext/CompositionGraph reference --
    planning is pure data derived from CompositionGraph's existing
    structure, not retained alongside it.

    Does not implement __iter__/__len__/__getitem__ in this version --
    use plan.steps directly (see module docstring).
    """

    steps: tuple[ExecutionStep, ...]


def plan(graph: CompositionGraph) -> ExecutionPlan:
    """Derive a deterministic ExecutionPlan from a valid CompositionGraph.

    Does not validate graph -- CompositionGraph.__post_init__ (ADR-016)
    already guarantees acyclicity, referential integrity, and no
    duplicate connections; plan() trusts that guarantee rather than
    re-checking it. Never calls any node's component.__call__. Does not
    mutate graph and does not retain a reference to it.
    """
    node_ids = tuple(node.id for node in graph.nodes)

    edges: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    in_degree: dict[str, int] = dict.fromkeys(node_ids, 0)
    dependencies: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for connection in graph.connections:
        edges[connection.source_node_id].append(connection.target_node_id)
        dependencies[connection.target_node_id].append(connection.source_node_id)
        in_degree[connection.target_node_id] += 1

    ready: deque[str] = deque(node_id for node_id in node_ids if in_degree[node_id] == 0)

    steps: list[ExecutionStep] = []
    while ready:
        node_id = ready.popleft()
        steps.append(ExecutionStep(node_id=node_id, dependencies=tuple(dependencies[node_id])))
        for neighbor in edges[node_id]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                ready.append(neighbor)

    return ExecutionPlan(steps=tuple(steps))
