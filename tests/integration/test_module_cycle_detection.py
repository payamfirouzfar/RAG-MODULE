"""Integration test: Step 19 module registration cycle detection through
real composition paths (Sequential), not only bare Module.register_module()
unit tests -- proving the invariant holds wherever registration actually
happens in this codebase, and that a rejected cycle leaves the graph
traversable through the public API (snapshot/inspect/named_modules)."""

from __future__ import annotations

import pytest

from ragtorch.core.errors import RegistryError
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class Echo(Module):
    def forward(self, input):
        return input


def test_sequential_cannot_be_registered_as_its_own_descendant():
    outer = Sequential(Echo())

    with pytest.raises(RegistryError, match="cycle"):
        outer[0].register_module("outer", outer)


def test_rejected_cycle_through_sequential_leaves_pipeline_functional():
    pipeline = Sequential(Echo(), Echo())

    with pytest.raises(RegistryError, match="cycle"):
        pipeline[1].register_module("pipeline", pipeline)

    # the pipeline itself is untouched and still executes correctly
    assert pipeline("hello") == "hello"
    assert [name for name, _ in pipeline.named_modules()] == [
        "Sequential",
        "step0",
        "step1",
    ]
    snapshot = pipeline.snapshot()
    assert len(snapshot.nodes) == 3
