"""Step 16 benchmark: measure Block's per-call overhead relative to a
direct component-chain invocation (ADR-020).

Run from the repository root with:
    python benchmarks/step16_block_composition.py

Block.forward() derives a fresh ExecutionPlan on every call (ADR-020
Q11, deliberately not cached in this version pending benchmark
evidence -- matching ADR-018's identical "measure before optimizing"
precedent for its own O(n^2) context-copying cost). This benchmark
measures the actual cost of that per-call plan() re-derivation plus
one ExecutionEngine.execute_plan() call, against a direct
hand-written component chain with no graph/plan/executor involved at
all, at small, fixed chain lengths (3/10/30 nodes) -- not a scaling
benchmark like ADR-017/018's, since Block adds a roughly constant
per-call cost on top of plan()'s own already-benchmarked
characteristics, not a new per-node cost.

As with every prior benchmark in this project: this measures, it does
not prove, an overhead claim. No threshold assertion is made; not
wired into CI as a blocking gate (matching Steps 13-15's precedent).
This measurement is the explicit evidence gate for ADR-020 Q11's
deferred plan-caching decision.
"""

from __future__ import annotations

import time

from ragtorch.core.block import Block
from ragtorch.core.composition import CompositionGraph, GraphNode
from ragtorch.core.connection import Connection
from ragtorch.core.ports import InputPort, OutputPort

CHAIN_LENGTHS = (3, 10, 30)
SAMPLES = 200


class Increment:
    name = "increment"
    component_type = "Increment"

    def __call__(self, value: int, *, context: object | None = None) -> int:
        return value + 1


def make_chain(length: int) -> list[Increment]:
    return [Increment() for _ in range(length)]


def run_direct(chain: list[Increment], value: int) -> int:
    for component in chain:
        value = component(value)
    return value


def make_block(length: int) -> Block:
    components = make_chain(length)
    nodes = tuple(GraphNode(id=f"n{i}", component=c) for i, c in enumerate(components))
    connections = tuple(
        Connection(
            source_node_id=f"n{i}",
            source_port=OutputPort(name="out", type=int),
            target_node_id=f"n{i + 1}",
            target_port=InputPort(name="in", type=int),
        )
        for i in range(length - 1)
    )
    graph = CompositionGraph(nodes=nodes, connections=connections)
    return Block(graph, input_node="n0", output_node=f"n{length - 1}")


def measure(fn, *, samples: int, warmup: int = 20) -> tuple[float, float]:
    for _ in range(warmup):
        fn()
    start = time.perf_counter()
    for _ in range(samples):
        fn()
    total = time.perf_counter() - start
    return total, (total / samples) * 1_000_000


def main() -> None:
    print("Step 16 measurements (Block vs. direct component-chain invocation):")
    print()
    header = (
        f"{'nodes':>6}  {'direct total (s)':>17}  {'direct us/call':>15}  "
        f"{'block total (s)':>16}  {'block us/call':>14}  {'overhead us/call':>17}"
    )
    print(header)

    for length in CHAIN_LENGTHS:
        chain = make_chain(length)
        direct_total, direct_us = measure(lambda chain=chain: run_direct(chain, 0), samples=SAMPLES)

        block = make_block(length)
        block_total, block_us = measure(lambda block=block: block(0), samples=SAMPLES)

        overhead_us = block_us - direct_us
        print(
            f"{length:>6}  {direct_total:>17.6f}  {direct_us:>15.4f}  "
            f"{block_total:>16.6f}  {block_us:>14.4f}  {overhead_us:>17.4f}"
        )

    print()
    print("Overhead is Block's per-call plan() re-derivation plus one")
    print("ExecutionEngine.execute_plan() call -- expected to be roughly")
    print("constant across these small chain lengths, not growing per node")
    print("the way ADR-018's own snapshot-copying cost does at much larger")
    print("scale (not re-measured here; see benchmarks/step14_execution_boundary.py).")


if __name__ == "__main__":
    main()
