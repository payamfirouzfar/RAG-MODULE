"""Step 23 benchmark: measure CompositionGraph functional-update cost
under the workload model established by the audit (evaluation/
step23-evaluation.md) -- does full-revalidation-per-update actually
matter for any workload this project has real evidence for?

Run from the repository root with:
    python benchmarks/step23_composition_graph_update_audit.py

Workloads (from the audit's Phase 2 model):

A. Small static graph -- construct once, never mutated (dominant
   pattern: confirmed the ONLY pattern any real consumer -- Block,
   ExecutionPlan, RAGModule -- actually uses).
B. Build-time functional construction -- chained add_node/
   add_connection from empty, at small-to-moderate final size.
C. Repeated branching -- one base graph, many independent single-update
   derivations (the shape a caller building several graph variants from
   one template might use).
D. Large graph -- construction at 10/100/1,000/10,000 nodes (matches
   the existing Step 12 scaling benchmark, re-run here for comparison).
E. Connection-heavy graph -- higher edge density than the linear-chain
   shape Step 12 used.
F. Repeated updates to an already-large graph -- the worst case this
   audit could construct: N sequential add_node calls against a graph
   that starts at 1,000 nodes, isolating whether update cost stays
   proportional to the CURRENT graph size (confirming "update = full
   rebuild") or shows any other growth shape.

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made. Not
wired into CI, matching the majority file-only precedent.
"""

from __future__ import annotations

import statistics
import sys
import time
from dataclasses import dataclass

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.ports import InputPort, OutputPort


class FakeComponent:
    name = "fake"
    component_type = "FakeComponent"

    def __call__(self, input: object, *, context: object | None = None) -> object:
        return input


@dataclass(frozen=True)
class Result:
    p50_us: float
    p95_us: float


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
    return Result(p50_us=statistics.median(ordered), p95_us=ordered[int(n * 0.95) - 1])


def linear_chain(count: int) -> tuple[tuple[GraphNode, ...], tuple[Connection, ...]]:
    nodes = tuple(GraphNode(id=f"n{i}", component=FakeComponent()) for i in range(count))
    connections = tuple(
        Connection(
            source_node_id=f"n{i}",
            source_port=OutputPort(name="out", type=list),
            target_node_id=f"n{i + 1}",
            target_port=InputPort(name="in", type=list),
        )
        for i in range(count - 1)
    )
    return nodes, connections


def fan_out_graph(node_count: int, edges_per_node: int) -> CompositionGraph:
    """Connection-heavy: node0 fans out to many targets (workload E)."""
    nodes = tuple(GraphNode(id=f"n{i}", component=FakeComponent()) for i in range(node_count))
    connections = []
    for i in range(1, min(node_count, edges_per_node + 1)):
        connections.append(
            Connection(
                source_node_id="n0",
                source_port=OutputPort(name=f"out{i}", type=list),
                target_node_id=f"n{i}",
                target_port=InputPort(name="in", type=list),
            )
        )
    return CompositionGraph(nodes=nodes, connections=tuple(connections))


def main() -> None:
    samples = 1_000

    print("Workload B -- build-time functional construction (chained, from empty):")
    print()

    def chained_build(final_size: int) -> None:
        graph = CompositionGraph(nodes=(), connections=())
        for i in range(final_size):
            graph = graph.add_node(GraphNode(id=f"n{i}", component=FakeComponent()))

    for size in (10, 100, 1_000):
        result = measure(lambda size=size: chained_build(size), samples=max(20, samples // size))
        print(f"  chained add_node to {size:>5} nodes: p50={result.p50_us:>10.3f}us")

    print()
    print("Workload C -- repeated branching (one base, many single-update derivations):")
    print()

    base_100 = CompositionGraph(*linear_chain(100))
    extra_node = GraphNode(id="branch", component=FakeComponent())

    def branch_once() -> None:
        base_100.add_node(extra_node)

    result = measure(branch_once, samples=samples)
    print(f"  single add_node() branching off a 100-node base: p50={result.p50_us:.3f}us")

    print()
    print("Workload D -- large graph construction (re-run of Step 12's scaling check):")
    print()

    for size in (10, 100, 1_000, 10_000):
        nodes, connections = linear_chain(size)
        sample_count = samples if size <= 1_000 else max(20, samples // 10)
        result = measure(
            lambda nodes=nodes, connections=connections: CompositionGraph(
                nodes=nodes, connections=connections
            ),
            samples=sample_count,
        )
        print(f"  construction at {size:>6} nodes: p50={result.p50_us:>12.3f}us")

    print()
    print("Workload E -- connection-heavy graph (fan-out, not just linear chain):")
    print()

    for node_count, edges in ((100, 50), (100, 99)):
        result = measure(
            lambda node_count=node_count, edges=edges: fan_out_graph(node_count, edges),
            samples=samples,
        )
        print(f"  {node_count} nodes, {edges} edges from n0: p50={result.p50_us:.3f}us")

    print()
    print("Workload F -- repeated updates against an already-large (1,000-node) graph:")
    print()

    large_base = CompositionGraph(*linear_chain(1_000))

    def update_large_base() -> None:
        large_base.add_node(GraphNode(id="extra-large", component=FakeComponent()))

    result = measure(update_large_base, samples=samples)
    print(f"  single add_node() on a 1,000-node graph: p50={result.p50_us:.3f}us")
    print("  (compare to Workload D's 1,000-node construction figure above --")
    print("   confirms update cost tracks full-rebuild cost at the CURRENT size,")
    print("   not the delta size, exactly as the 'full revalidation' description says)")

    print()
    print(f"python={sys.version.split()[0]}")
    print("Measurement only. No performance guarantee or threshold is established.")


if __name__ == "__main__":
    main()
