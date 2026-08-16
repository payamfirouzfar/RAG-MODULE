"""Integration test: a realistic multi-level tree snapshots correctly,
and Module.inspect() (migrated to be snapshot-backed, ADR-012) still
produces its pre-existing, backward-compatible text output — proving
Module -> snapshot -> inspect is one canonical representation, not two
independent tree walks."""

from __future__ import annotations

from ragtorch.core.inspection import snapshot
from ragtorch.core.module import Module
from ragtorch.core.sequential import Sequential


class Retriever(Module):
    def forward(self, input):
        return input


class Reranker(Module):
    def forward(self, input):
        return input


class Generator(Module):
    def forward(self, input):
        return input


class Pipeline(Module):
    def __init__(self):
        super().__init__()
        self.retriever = Retriever()
        self.reranker = Reranker()
        self.generator = Generator()

    def forward(self, input):
        return input


def test_snapshot_matches_actual_module_hierarchy():
    pipeline = Pipeline()
    snap = snapshot(pipeline)

    node_ids = {n.id for n in snap.nodes}
    assert node_ids == {"Pipeline", "retriever", "reranker", "generator"}

    child_pairs = {(c.parent_id, c.child_id) for c in snap.children}
    assert child_pairs == {
        ("Pipeline", "retriever"),
        ("Pipeline", "reranker"),
        ("Pipeline", "generator"),
    }

    types_by_id = {n.id: n.component_type for n in snap.nodes}
    assert types_by_id["retriever"] == "Retriever"
    assert types_by_id["reranker"] == "Reranker"
    assert types_by_id["generator"] == "Generator"


def test_inspect_output_unchanged_for_realistic_pipeline():
    pipeline = Pipeline()
    out = pipeline.inspect()
    assert "Modules: 4" in out
    assert "Depth: 2" in out
    assert "retriever (Retriever)" in out
    assert "reranker (Reranker)" in out
    assert "generator (Generator)" in out


def test_snapshot_over_sequential_composite():
    seq = Sequential(Retriever(), Reranker(), Generator())
    snap = snapshot(seq)
    node_ids = {n.id for n in snap.nodes}
    assert node_ids == {"Sequential", "step0", "step1", "step2"}
