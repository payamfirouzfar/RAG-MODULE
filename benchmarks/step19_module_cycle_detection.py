"""Step 19 benchmark: measure the registration-time cost of cycle
detection (_would_create_cycle) as the prospective child's subtree
grows.

Run from the repository root with:
    python benchmarks/step19_module_cycle_detection.py

_would_create_cycle walks the prospective child's descendant subtree
once per registration -- O(number of descendants). This benchmark
establishes a baseline shape (does cost grow roughly linearly with
subtree size, as expected, or is there a surprise), not a performance
guarantee. As with every prior benchmark in this project: this
measures, it does not prove, an overhead claim; no threshold assertion
is made; not wired into CI (matching the majority -- 12 of 13 prior
benchmarks -- file-only precedent established during Step 18's own
18H-1/18H-2 audit; Step 18's benchmark is the deliberate, justified
exception, not the default).
"""

from __future__ import annotations

import time

from ragtorch.core.module import Module

CHAIN_LENGTHS = (1, 10, 100, 1_000)
SAMPLES = 500


class Leaf(Module):
    def forward(self, input):
        return input


def make_chain(length: int) -> Module:
    """A linear chain of `length` nested modules -- the worst case for
    _would_create_cycle's subtree walk (no branching, every node visited)."""
    root = Leaf()
    current = root
    for _ in range(length - 1):
        child = Leaf()
        current.register_module("next", child)
        current = child
    return root


def measure(fn, *, samples: int, warmup: int = 20) -> tuple[float, float]:
    for _ in range(warmup):
        fn()
    start = time.perf_counter()
    for _ in range(samples):
        fn()
    total = time.perf_counter() - start
    return total, (total / samples) * 1_000_000


def main() -> None:
    print("Step 19 measurements (register_module cost vs. prospective child's subtree size):")
    print()
    header = f"{'subtree size':>13}  {'total (s)':>12}  {'us/call':>12}"
    print(header)

    for length in CHAIN_LENGTHS:
        chain = make_chain(length)

        def register_and_detach(chain=chain):
            parent = Leaf()
            parent.register_module("child", chain)
            # detach for the next iteration to avoid re-registering
            # the same (name, instance) pair repeatedly under a
            # different parent, which would still be valid (a shared
            # child under different parents is not a cycle) but would
            # not reflect a fresh registration's true cost as cleanly.
            del parent._modules["child"]

        total, per_call_us = measure(register_and_detach, samples=SAMPLES)
        print(f"{length:>13}  {total:>12.6f}  {per_call_us:>12.4f}")

    print()
    print("Cost is expected to grow roughly with subtree size (O(descendants)),")
    print("since _would_create_cycle walks the prospective child's full subtree")
    print("once per registration. Measurement only -- no threshold is established.")


if __name__ == "__main__":
    main()
