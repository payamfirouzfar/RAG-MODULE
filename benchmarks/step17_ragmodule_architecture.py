"""Step 17 benchmark: measure RAGModule.from_graph's additional
per-call overhead over calling Block directly (ADR-021).

Run from the repository root with:
    python benchmarks/step17_ragmodule_architecture.py

RAGModule.from_graph(...) returns a _GraphBackedRAGModule wrapping a
Block. Calling the result goes through one additional Module.__call__
layer (_GraphBackedRAGModule's own event-publishing and
exception-wrapping) before reaching Block.forward -- this benchmark
isolates that additional layer's cost from Block's own already-
benchmarked per-call cost (ADR-020, benchmarks/step16_block_composition.py),
at the same small, fixed chain lengths (3/10/30 nodes) Step 16 used,
since the added cost is one more Module.__call__ invocation, not a
new per-node cost.

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made; not
wired into CI as a blocking gate (matching Steps 13-16's precedent).
"""

from __future__ import annotations

import time

from ragtorch.core.block import Block
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.module import RAGModule
from ragtorch.core.ports import InputPort, OutputPort

CHAIN_LENGTHS = (3, 10, 30)
SAMPLES = 200


class Increment:
    name = "increment"
    component_type = "Increment"

    def __call__(self, value: int, *, context: object | None = None) -> int:
        return value + 1


def make_graph(length: int) -> CompositionGraph:
    nodes = tuple(GraphNode(id=f"n{i}", component=Increment()) for i in range(length))
    connections = tuple(
        Connection(
            source_node_id=f"n{i}",
            source_port=OutputPort(name="out", type=int),
            target_node_id=f"n{i + 1}",
            target_port=InputPort(name="in", type=int),
        )
        for i in range(length - 1)
    )
    return CompositionGraph(nodes=nodes, connections=connections)


def measure(fn, *, samples: int, warmup: int = 20) -> tuple[float, float]:
    for _ in range(warmup):
        fn()
    start = time.perf_counter()
    for _ in range(samples):
        fn()
    total = time.perf_counter() - start
    return total, (total / samples) * 1_000_000


def main() -> None:
    print("Step 17 measurements (RAGModule.from_graph overhead over calling Block directly):")
    print()
    header = (
        f"{'nodes':>6}  {'block total (s)':>16}  {'block us/call':>14}  "
        f"{'ragmodule total (s)':>19}  {'ragmodule us/call':>17}  {'overhead us/call':>17}"
    )
    print(header)

    for length in CHAIN_LENGTHS:
        graph_for_block = make_graph(length)
        block = Block(graph_for_block, input_node="n0", output_node=f"n{length - 1}")
        block_total, block_us = measure(lambda block=block: block(0), samples=SAMPLES)

        graph_for_ragmodule = make_graph(length)
        architecture = RAGModule.from_graph(
            graph_for_ragmodule, input_node="n0", output_node=f"n{length - 1}"
        )
        ragmodule_total, ragmodule_us = measure(
            lambda architecture=architecture: architecture(0), samples=SAMPLES
        )

        overhead_us = ragmodule_us - block_us
        print(
            f"{length:>6}  {block_total:>16.6f}  {block_us:>14.4f}  "
            f"{ragmodule_total:>19.6f}  {ragmodule_us:>17.4f}  {overhead_us:>17.4f}"
        )

    print()
    print("Overhead is the additional Module.__call__ layer")
    print("(_GraphBackedRAGModule's own event-publishing/exception-wrapping) on")
    print("top of Block's own already-benchmarked per-call cost -- expected to be")
    print("small and roughly constant, not growing with graph size.")


if __name__ == "__main__":
    main()
