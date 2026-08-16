"""Step 9 benchmark: measure architecture validation overhead (ADR-013).

Run from the repository root with:
    python benchmarks/step9_architecture_validation.py

Measures validate_snapshot() on valid trees of 1/10/100/1,000 nodes
(built via the real Module -> snapshot() path, not hand-constructed
dataclasses) to empirically check the O(N + E) design: doubling N
should roughly double runtime, not quadruple it. Also measures two
failure cases (duplicate node id — fails at the earliest check; a
disconnected cycle attached to an otherwise-valid tree — fails only
after the reachability walk, the most expensive check to reach) to
show how quickly an invalid architecture is rejected at each stage.

This is a baseline tool, not a performance test with a hard
machine-independent threshold — consistent with the Step 5-8
benchmarks' methodology and the project's anti-flakiness policy.
Numbers are measured and reported as-is, not optimized toward a target.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from ragtorch.core.architecture import validate_snapshot
from ragtorch.core.errors import ValidationError
from ragtorch.core.inspection import ArchitectureChild, ArchitectureNode, ArchitectureSnapshot
from ragtorch.core.module import Module


class Leaf(Module):
    def forward(self, input: int) -> int:
        return input


class FlatContainer(Module):
    """A single-level container with N leaf children."""

    def __init__(self, count: int) -> None:
        super().__init__()
        for i in range(count):
            setattr(self, f"leaf{i}", Leaf())


@dataclass(frozen=True)
class Result:
    name: str
    p50_us: float
    p95_us: float
    p99_us: float


def measure(fn, *, samples: int, warmup: int = 200) -> Result:
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


def flat_snapshot(count: int) -> ArchitectureSnapshot:
    return FlatContainer(count).snapshot()


def duplicate_id_snapshot() -> ArchitectureSnapshot:
    node = ArchitectureNode(id="A", name="A", component_type="X")
    return ArchitectureSnapshot(nodes=(node, node), children=())


def unreachable_snapshot(count: int) -> ArchitectureSnapshot:
    """A valid tree rooted at "0" plus a disconnected 2-node mutual
    cycle ("cyc-a" <-> "cyc-b"). Neither cycle node has zero incoming
    edges (each is the other's parent), so root-counting alone still
    finds exactly one root ("0") - the disconnected pair is only
    caught by the reachability walk. Mirrors ADR-013's disconnected-
    cycle test case, at benchmark scale."""
    nodes = tuple(
        ArchitectureNode(id=str(i), name=str(i), component_type="X") for i in range(count)
    ) + (
        ArchitectureNode(id="cyc-a", name="cyc-a", component_type="X"),
        ArchitectureNode(id="cyc-b", name="cyc-b", component_type="X"),
    )
    children = (
        tuple(ArchitectureChild(parent_id="0", child_id=str(i)) for i in range(1, count))
        + (ArchitectureChild(parent_id="cyc-a", child_id="cyc-b"),)
        + (ArchitectureChild(parent_id="cyc-b", child_id="cyc-a"),)
    )
    return ArchitectureSnapshot(nodes=nodes, children=children)


def main() -> None:
    samples = 5_000
    snap_1 = flat_snapshot(1)
    snap_10 = flat_snapshot(10)
    snap_100 = flat_snapshot(100)
    snap_1000 = flat_snapshot(1000)
    dup_snap = duplicate_id_snapshot()
    unreachable_snap = unreachable_snapshot(100)

    def validate_1() -> None:
        validate_snapshot(snap_1)

    def validate_10() -> None:
        validate_snapshot(snap_10)

    def validate_100() -> None:
        validate_snapshot(snap_100)

    def validate_1000() -> None:
        validate_snapshot(snap_1000)

    def validate_duplicate() -> None:
        try:
            validate_snapshot(dup_snap)
        except ValidationError:
            pass

    def validate_unreachable() -> None:
        try:
            validate_snapshot(unreachable_snap)
        except ValidationError:
            pass

    results = {
        "validate_snapshot() - 1 node": measure(validate_1, samples=samples),
        "validate_snapshot() - 10 nodes": measure(validate_10, samples=samples),
        "validate_snapshot() - 100 nodes": measure(validate_100, samples=samples),
        "validate_snapshot() - 1000 nodes": measure(validate_1000, samples=samples // 2),
        "validate_snapshot() - duplicate id (fails fast)": measure(
            validate_duplicate, samples=samples
        ),
        "validate_snapshot() - disconnected cycle, 100 nodes (fails after reachability)": measure(
            validate_unreachable, samples=samples
        ),
    }

    print(f"samples={samples}")
    print()
    print("Step 9 measurements:")
    for label, result in results.items():
        print(f"  {label}")
        print(f"    p50={result.p50_us:.3f}us p95={result.p95_us:.3f}us p99={result.p99_us:.3f}us")

    print()
    print("Scaling check (p50, expect roughly linear growth as N grows 1 -> 10 -> 100 -> 1000):")
    for label in (
        "validate_snapshot() - 1 node",
        "validate_snapshot() - 10 nodes",
        "validate_snapshot() - 100 nodes",
        "validate_snapshot() - 1000 nodes",
    ):
        print(f"  {label}: {results[label].p50_us:.3f}us")


if __name__ == "__main__":
    main()
