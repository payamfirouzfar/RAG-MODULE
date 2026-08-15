from __future__ import annotations

import pytest

from ragtorch.core.trace import Trace


def test_single_span_records_timing_and_ok_status():
    trace = Trace()
    with trace.start_span("retriever") as span:
        pass
    assert span.status == "ok"
    assert span.duration is not None
    assert span.duration >= 0


def test_span_failure_sets_error_status():
    trace = Trace()
    with pytest.raises(ValueError):
        with trace.start_span("generator"):
            raise ValueError("boom")
    span = trace.spans[0]
    assert span.status == "error"
    assert span.duration is not None


def test_nested_spans_record_parent_child_relationship():
    trace = Trace()
    with trace.start_span("pipeline") as root:
        with trace.start_span("retriever") as child:
            pass
    assert child.parent_span_id == root.span_id
    assert root.parent_span_id is None


def test_root_spans_returns_only_top_level():
    trace = Trace()
    with trace.start_span("pipeline"):
        with trace.start_span("retriever"):
            pass
    roots = trace.root_spans()
    assert len(roots) == 1
    assert roots[0].name == "pipeline"


def test_children_of_returns_direct_children_only():
    trace = Trace()
    with trace.start_span("pipeline") as root:
        with trace.start_span("retriever"):
            with trace.start_span("vector_search"):
                pass
    children = trace.children_of(root.span_id)
    assert len(children) == 1
    assert children[0].name == "retriever"


def test_sibling_spans_share_parent():
    trace = Trace()
    with trace.start_span("pipeline") as root:
        with trace.start_span("chunker"):
            pass
        with trace.start_span("retriever"):
            pass
    children = trace.children_of(root.span_id)
    assert {c.name for c in children} == {"chunker", "retriever"}


def test_span_attributes_are_stored():
    trace = Trace()
    with trace.start_span("retriever", top_k=5) as span:
        pass
    assert span.attributes == {"top_k": 5}


def test_render_produces_indented_tree():
    trace = Trace()
    with trace.start_span("pipeline"):
        with trace.start_span("retriever"):
            pass
    out = trace.render()
    lines = out.splitlines()
    assert lines[0].startswith("pipeline")
    assert lines[1].startswith("    retriever")


def test_empty_trace_renders_empty_string():
    trace = Trace()
    assert trace.render() == ""
