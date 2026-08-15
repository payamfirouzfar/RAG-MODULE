from __future__ import annotations

import dataclasses

import pytest

from ragtorch.core.context import ExecutionContext, new_run_id


def test_new_run_id_is_unique():
    assert new_run_id() != new_run_id()


def test_new_run_id_has_expected_prefix():
    assert new_run_id().startswith("run_")


def test_default_context_has_run_id_and_no_parent():
    ctx = ExecutionContext()
    assert ctx.run_id.startswith("run_")
    assert ctx.parent_run_id is None
    assert dict(ctx.metadata) == {}


def test_context_accepts_explicit_metadata():
    ctx = ExecutionContext(metadata={"module": "retriever"})
    assert ctx.metadata["module"] == "retriever"


def test_context_is_frozen():
    ctx = ExecutionContext()
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.run_id = "other"


def test_context_metadata_is_not_externally_mutable():
    source = {"key": "value"}
    ctx = ExecutionContext(metadata=source)
    source["key"] = "mutated"
    assert ctx.metadata["key"] == "value"

    with pytest.raises(TypeError):
        ctx.metadata["key"] = "mutated"  # type: ignore[index]


def test_child_gets_new_run_id_and_records_parent():
    parent = ExecutionContext()
    child = parent.child()
    assert child.run_id != parent.run_id
    assert child.parent_run_id == parent.run_id


def test_child_merges_metadata_on_top_of_parent():
    parent = ExecutionContext(metadata={"a": 1, "b": 1})
    child = parent.child(b=2, c=3)
    assert dict(child.metadata) == {"a": 1, "b": 2, "c": 3}
    # parent unaffected
    assert dict(parent.metadata) == {"a": 1, "b": 1}


def test_nested_children_chain_parent_ids():
    root = ExecutionContext()
    mid = root.child()
    leaf = mid.child()
    assert leaf.parent_run_id == mid.run_id
    assert mid.parent_run_id == root.run_id
