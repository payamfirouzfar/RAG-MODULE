"""Step 13 benchmark: measure plan() construction and scaling
characteristics (ADR-017).

Run from the repository root with:
    python benchmarks/step13_execution_plan.py

Measures plan() at 10/100/1,000/10,000 nodes across three shapes:
  - linear chain: node[i] -> node[i+1], one connection each
  - wide: one root fanning out to N-1 independent leaves
  - diamond-heavy: alternating fan-out/fan-in layers

as informational scaling evidence for the O(V+E) design target, not a
hard performance gate. Consistent with the Step 5-12 benchmarks'
methodology and the project's anti-flakiness policy: numbers are
measured and reported as-is, not optimized toward a target, and no
threshold assertion is made that could make CI flaky.

Step 12's own benchmark caught a real RecursionError bug in
CompositionGraph._has_cycle() specifically by testing at 1,000 nodes
that no small hand-built unit test exercised. plan() reuses an
iterative (not recursive) FIFO Kahn's algorithm from the start, so no
equivalent recursion-depth failure is expected here -- this benchmark
exists to check that observed scaling is consistent with the intended
O(V+E) algorithm at the tested sizes/shapes, and to catch a regression
if a future change makes plan() accidentally quadratic. A benchmark
cannot mathematically prove an asymptotic complexity bound; it can
only show measurements that are, or are not, consistent with one.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.execution_plan import plan
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


def measure(fn, *, samples: int, warmup: int = 20) -> Result:
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


def linear_chain(count: int) -> CompositionGraph:
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
    return CompositionGraph(nodes=nodes, connections=connections)


def wide_graph(count: int) -> CompositionGraph:
    """One root fanning out to count - 1 independent leaves."""
    nodes = tuple(GraphNode(id=f"n{i}", component=FakeComponent()) for i in range(count))
    connections = tuple(
        Connection(
            source_node_id="n0",
            source_port=OutputPort(name=f"out{i}", type=list),
            target_node_id=f"n{i}",
            target_port=InputPort(name="in", type=list),
        )
        for i in range(1, count)
    )
    return CompositionGraph(nodes=nodes, connections=connections)


def diamond_heavy_graph(layer_count: int, layer_width: int) -> CompositionGraph:
    """Alternating fan-out/fan-in layers: each node in layer i connects
    to every node in layer i+1, each via a distinct named port pair."""
    nodes: list[GraphNode] = []
    connections: list[Connection] = []
    layers: list[list[str]] = []
    for layer_index in range(layer_count):
        layer_ids = [f"l{layer_index}n{i}" for i in range(layer_width)]
        layers.append(layer_ids)
        for node_id in layer_ids:
            nodes.append(GraphNode(id=node_id, component=FakeComponent()))

    for layer_index in range(layer_count - 1):
        for source_id in layers[layer_index]:
            for target_id in layers[layer_index + 1]:
                connections.append(
                    Connection(
                        source_node_id=source_id,
                        source_port=OutputPort(name=f"out_{target_id}", type=list),
                        target_node_id=target_id,
                        target_port=InputPort(name=f"in_{source_id}", type=list),
                    )
                )
    return CompositionGraph(nodes=tuple(nodes), connections=tuple(connections))


def main() -> None:
    samples = 200

    linear_graphs = {n: linear_chain(n) for n in (10, 100, 1_000, 10_000)}
    wide_graphs = {n: wide_graph(n) for n in (10, 100, 1_000, 10_000)}
    diamond_graph_small = diamond_heavy_graph(layer_count=4, layer_width=5)  # 20 nodes
    diamond_graph_large = diamond_heavy_graph(layer_count=4, layer_width=15)  # 60 nodes

    results: dict[str, Result] = {}

    for n, graph in linear_graphs.items():

        def run(g: CompositionGraph = graph) -> None:
            plan(g)

        results[f"plan() - linear chain, {n} nodes"] = measure(
            run, samples=samples if n <= 1_000 else 40
        )

    for n, graph in wide_graphs.items():

        def run(g: CompositionGraph = graph) -> None:
            plan(g)

        results[f"plan() - wide fan-out, {n} nodes"] = measure(
            run, samples=samples if n <= 1_000 else 40
        )

    def run_diamond_small() -> None:
        plan(diamond_graph_small)

    def run_diamond_large() -> None:
        plan(diamond_graph_large)

    results["plan() - diamond-heavy, 20 nodes (4x5)"] = measure(run_diamond_small, samples=samples)
    results["plan() - diamond-heavy, 60 nodes (4x15)"] = measure(run_diamond_large, samples=samples)

    print(f"samples={samples} (reduced for N>=10,000)")
    print()
    print("Step 13 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")

    print()
    print("Scaling check (p50, linear chain, expect roughly linear growth 10->100->1000->10000):")
    for n in (10, 100, 1_000, 10_000):
        label = f"plan() - linear chain, {n} nodes"
        print(f"  {label}: {results[label].p50_us:.3f}us")

    print()
    print("Scaling check (p50, wide fan-out, expect roughly linear growth 10->100->1000->10000):")
    for n in (10, 100, 1_000, 10_000):
        label = f"plan() - wide fan-out, {n} nodes"
        print(f"  {label}: {results[label].p50_us:.3f}us")


if __name__ == "__main__":
    main()
