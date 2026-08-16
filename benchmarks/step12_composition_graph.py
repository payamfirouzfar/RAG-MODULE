"""Step 12 benchmark: measure CompositionGraph construction and
operation overhead, including scaling characteristics (ADR-016).

Run from the repository root with:
    python benchmarks/step12_composition_graph.py

Measures CompositionGraph construction at 10/100/1,000 nodes (a linear
chain: node[i] -> node[i+1], one connection each) as informational
scaling evidence -- is validation roughly linear in node/connection
count, or does it silently become O(N^2)? Also measures single-operation
cost (add_node, add_connection) and how quickly the two failure paths
(duplicate connection, cycle) are rejected.

Running this benchmark at 1,000 nodes caught a real bug before this
benchmark file was committed: the first cycle-detection implementation
used recursive DFS, which raised RecursionError on a 1,000-node linear
chain (Python's default recursion limit is 1,000). Fixed by rewriting
_has_cycle() as an iterative Kahn's-algorithm topological sort, which
has no recursion depth dependent on graph size. This is the concrete
reason this project always benchmarks at multiple scales rather than
trusting correctness at a single small size.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5-11
benchmarks' methodology and the project's anti-flakiness policy.
Numbers are measured and reported as-is, not optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.errors import ValidationError
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float
    p99_us: float


def measure(fn, *, samples: int, warmup: int = 50) -> Result:
    for _ in range(warmup):
        fn()

    values: list[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        fn()
        values.append((time.perf_counter_ns() - start) / 1_000.0)
    ordered = sorted(values)
    n = len(ordered)
    return Result(
        name=fn.__name__ if hasattr(fn, "__name__") else "anonymous",
        p50_us=statistics.median(ordered),
        p95_us=ordered[int(n * 0.95) - 1],
        p99_us=ordered[int(n * 0.99) - 1],
    )


def linear_chain_args(
    count: int,
) -> tuple[tuple[GraphNode, ...], tuple[Connection, ...]]:
    nodes = tuple(GraphNode(id=f"node{i}", component=FakeComponent()) for i in range(count))
    connections = tuple(
        Connection(
            source_node_id=f"node{i}",
            source_port=OutputPort(name="out", type=list),
            target_node_id=f"node{i + 1}",
            target_port=InputPort(name="in", type=list),
        )
        for i in range(count - 1)
    )
    return nodes, connections


def main() -> None:
    samples = 2_000

    nodes_10, connections_10 = linear_chain_args(10)
    nodes_100, connections_100 = linear_chain_args(100)
    nodes_1000, connections_1000 = linear_chain_args(1000)

    base_graph = CompositionGraph(nodes=nodes_100, connections=connections_100)
    new_node = GraphNode(id="extra", component=FakeComponent())
    graph_with_extra_node = base_graph.add_node(new_node)
    new_connection = Connection(
        source_node_id="node0",
        source_port=OutputPort(name="out2", type=list),
        target_node_id="extra",
        target_port=InputPort(name="in", type=list),
    )

    duplicate_connection = connections_100[0]
    cycle_nodes = (
        GraphNode(id="a", component=FakeComponent()),
        GraphNode(id="b", component=FakeComponent()),
    )
    cycle_connections = (
        Connection(
            source_node_id="a",
            source_port=OutputPort(name="out", type=list),
            target_node_id="b",
            target_port=InputPort(name="in", type=list),
        ),
        Connection(
            source_node_id="b",
            source_port=OutputPort(name="out", type=list),
            target_node_id="a",
            target_port=InputPort(name="in", type=list),
        ),
    )

    def construct_10() -> None:
        CompositionGraph(nodes=nodes_10, connections=connections_10)

    def construct_100() -> None:
        CompositionGraph(nodes=nodes_100, connections=connections_100)

    def construct_1000() -> None:
        CompositionGraph(nodes=nodes_1000, connections=connections_1000)

    def op_add_node() -> None:
        base_graph.add_node(new_node)

    def op_add_connection() -> None:
        graph_with_extra_node.add_connection(new_connection)

    def fail_duplicate_connection() -> None:
        try:
            CompositionGraph(nodes=nodes_100, connections=(*connections_100, duplicate_connection))
        except ValidationError:
            pass

    def fail_cycle() -> None:
        try:
            CompositionGraph(nodes=cycle_nodes, connections=cycle_connections)
        except ValidationError:
            pass

    results = {
        "CompositionGraph construction - 10 nodes": measure(construct_10, samples=samples),
        "CompositionGraph construction - 100 nodes": measure(construct_100, samples=samples),
        "CompositionGraph construction - 1000 nodes": measure(construct_1000, samples=samples // 4),
        "add_node() on 100-node graph": measure(op_add_node, samples=samples),
        "add_connection() on 100-node graph": measure(op_add_connection, samples=samples),
        "construction - duplicate connection (fails fast)": measure(
            fail_duplicate_connection, samples=samples
        ),
        "construction - two-node cycle (fails after cycle check)": measure(
            fail_cycle, samples=samples
        ),
    }

    print(f"samples={samples}")
    print()
    print("Step 12 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")

    print()
    print("Scaling check (p50, expect roughly linear growth as N grows 10 -> 100 -> 1000):")
    for label in (
        "CompositionGraph construction - 10 nodes",
        "CompositionGraph construction - 100 nodes",
        "CompositionGraph construction - 1000 nodes",
    ):
        print(f"  {label}: {results[label].p50_us:.3f}us")


if __name__ == "__main__":
    main()
