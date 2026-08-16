"""Integration test: a real Module tree's snapshot passes validation,
and inspect() still works on an already-validated snapshot (ADR-013).

Proves the validator accepts what the real system actually produces,
not only hand-built dataclass fixtures - and that validate_snapshot()
is an explicit caller choice, not something inspect()/snapshot()
implicitly perform."""

from __future__ import annotations

from ragtorch.core.architecture import validate_snapshot
from ragtorch.core.module import Module


class Reranker(Module):
    def forward(self, input):
        return input


class Retriever(Module):
    def __init__(self):
        super().__init__()
        self.reranker = Reranker()

    def forward(self, input):
        return input


class Generator(Module):
    def forward(self, input):
        return input


class Pipeline(Module):
    def __init__(self):
        super().__init__()
        self.retriever = Retriever()
        self.generator = Generator()

    def forward(self, input):
        return input


def test_real_module_tree_snapshot_passes_validation():
    pipeline = Pipeline()
    snap = pipeline.snapshot()
    assert validate_snapshot(snap) is None


def test_validated_snapshot_still_supports_inspect():
    pipeline = Pipeline()
    snap = pipeline.snapshot()
    validate_snapshot(snap)  # no exception
    text = pipeline.inspect()
    assert "retriever (Retriever)" in text
    assert "generator (Generator)" in text
    assert "reranker (Reranker)" in text


def test_single_leaf_module_snapshot_passes_validation():
    generator = Generator()
    assert validate_snapshot(generator.snapshot()) is None
