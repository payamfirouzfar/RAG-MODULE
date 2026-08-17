"""Integration test: ADR-022 execution-scoped event delivery through the
real composition paths (Sequential, nested Module, Block, RAGModule,
ExecutionEngine) -- not merely through Module.__call__ unit tests.

Scope is deliberately narrow: prove the frozen ADR-022 contract holds
through real production execution paths. Does not modify production
architecture -- see the 18F repository audit (Sequential.forward is the
only .child() call site; ExecutionEngine.execute/execute_plan and
Block.forward thread a caller-supplied context straight through
unmodified, without touching event_scope themselves).
"""

from __future__ import annotations

import threading

import pytest

from ragtorch import (
    Block,
    CompositionGraph,
    Connection,
    Event,
    EventScope,
    EventType,
    ExecutionContext,
    ExecutionEngine,
    GraphNode,
    InputPort,
    Module,
    OutputPort,
    RAGModule,
    Sequential,
    event_bus,
)
from ragtorch.core.errors import ExecutionError, ListenerDeliveryError


class Retriever(Module):
    def forward(self, query, *, context=None):
        return [f"doc-about-{query}", "doc-b"]


class Reranker(Module):
    def forward(self, docs, *, context=None):
        return list(reversed(docs))


class Generator(Module):
    def forward(self, docs, *, context=None):
        return f"answer using {docs}"


class FailingStage(Module):
    def forward(self, value, *, context=None):
        raise ValueError("stage exploded")


def rag_graph() -> CompositionGraph:
    return CompositionGraph(
        nodes=(
            GraphNode(id="retrieve", component=Retriever()),
            GraphNode(id="rerank", component=Reranker()),
            GraphNode(id="generate", component=Generator()),
        ),
        connections=(
            Connection(
                source_node_id="retrieve",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="rerank",
                target_port=InputPort(name="docs", type=list),
            ),
            Connection(
                source_node_id="rerank",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="generate",
                target_port=InputPort(name="docs", type=list),
            ),
        ),
    )


def failing_graph() -> CompositionGraph:
    return CompositionGraph(
        nodes=(
            GraphNode(id="retrieve", component=Retriever()),
            GraphNode(id="fail", component=FailingStage()),
        ),
        connections=(
            Connection(
                source_node_id="retrieve",
                source_port=OutputPort(name="docs", type=list),
                target_node_id="fail",
                target_port=InputPort(name="docs", type=list),
            ),
        ),
    )


def test_sequential_propagates_event_scope_to_children():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    pipeline = Sequential(Retriever(), Reranker(), Generator())
    pipeline("hello", context=context)

    module_names = {e.module_name for e in received}
    assert module_names == {"Sequential", "Retriever", "Reranker", "Generator"}


def test_nested_module_execution_stays_in_same_scope():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    inner = Sequential(Retriever(), Reranker())
    outer = Sequential(inner, Generator())
    outer(1, context=context)

    # every event's run_id traces back into one connected tree rooted
    # at the top-level context's run_id -- proving .child() propagation
    # holds across two levels of Sequential nesting, not just one.
    run_ids = {context.run_id} | {e.run_id for e in received}
    assert all(e.parent_run_id is None or e.parent_run_id in run_ids for e in received)
    assert {"Sequential", "Retriever", "Reranker", "Generator"} == {e.module_name for e in received}


def test_block_propagates_event_scope_to_internal_nodes():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    block = Block(rag_graph(), input_node="retrieve", output_node="generate")
    block(1, context=context)

    module_names = {e.module_name for e in received}
    # Block is itself a Module, so it publishes its own lifecycle
    # events in addition to its internal graph nodes' events.
    assert module_names == {"Block", "Retriever", "Reranker", "Generator"}
    # Block.forward threads the SAME context object to every internal
    # node (no per-node .child()) -- so every delivered event shares
    # the top-level context's run_id, not a derived one.
    assert all(e.run_id == context.run_id for e in received)


def test_rag_module_propagates_event_scope():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    architecture = RAGModule.from_graph(rag_graph(), input_node="retrieve", output_node="generate")
    architecture("What is RAG?", context=context)

    module_names = {e.module_name for e in received}
    assert "_GraphBackedRAGModule" in module_names
    assert {"Retriever", "Reranker", "Generator"} <= module_names


def test_execution_engine_propagates_event_scope():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    engine = ExecutionEngine()
    pipeline = Sequential(Retriever(), Reranker())
    result = engine.execute(pipeline, "hello", context=context)

    assert result.run.context.run_id == context.run_id
    module_names = {e.module_name for e in received}
    assert {"Sequential", "Retriever", "Reranker"} <= module_names


def test_failure_events_reach_execution_scope():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    pipeline = Sequential(Retriever(), FailingStage())

    with pytest.raises(ExecutionError):
        pipeline("query", context=context)

    failing_events = [e for e in received if e.module_name == "FailingStage"]
    assert [e.type for e in failing_events] == [
        EventType.MODULE_STARTED,
        EventType.MODULE_FAILED,
    ]


def test_block_failure_propagates_to_event_scope():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    block = Block(failing_graph(), input_node="retrieve", output_node="fail")

    with pytest.raises(ExecutionError):
        block(1, context=context)

    failing_events = [e for e in received if e.module_name == "FailingStage"]
    assert EventType.MODULE_FAILED in [e.type for e in failing_events]


def test_independent_executions_do_not_cross_scope_boundaries():
    scope_a = EventScope()
    scope_b = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope_a.subscribe(received_a.append)
    scope_b.subscribe(received_b.append)

    context_a = ExecutionContext(event_scope=scope_a)
    context_b = ExecutionContext(event_scope=scope_b)

    Sequential(Retriever(), Reranker())("query-a", context=context_a)
    Sequential(Retriever(), Reranker())("query-b", context=context_b)

    run_ids_a = {context_a.run_id} | {e.run_id for e in received_a}
    run_ids_b = {context_b.run_id} | {e.run_id for e in received_b}
    assert run_ids_a.isdisjoint(run_ids_b)
    assert all(e.run_id in run_ids_a for e in received_a)
    assert all(e.run_id in run_ids_b for e in received_b)


def test_global_bus_remains_independent_of_execution_scope():
    scope = EventScope()
    scoped_received: list[Event] = []
    global_received: list[Event] = []
    scope.subscribe(scoped_received.append)

    bus = event_bus()
    bus.subscribe(global_received.append)
    try:
        context = ExecutionContext(event_scope=scope)
        Sequential(Retriever(), Reranker())("query", context=context)
    finally:
        bus.unsubscribe(global_received.append)

    # Children under Sequential receive .child()-derived contexts, so
    # filter by tracing the run_id graph rather than requiring an exact
    # run_id match against the root context.
    root_and_children_ids = {context.run_id} | {
        e.run_id for e in global_received if e.parent_run_id == context.run_id
    }
    global_filtered = [e for e in global_received if e.run_id in root_and_children_ids]
    # global bus sees this execution's events regardless of scoping --
    # scoping is additive, never a replacement for global delivery.
    assert global_filtered
    assert {e.module_name for e in global_filtered} >= {"Sequential", "Retriever", "Reranker"}
    # a context WITHOUT event_scope run elsewhere must not appear in
    # the scoped listener's results.
    unscoped_context = ExecutionContext()
    Sequential(Retriever())("other query", context=unscoped_context)
    assert all(e.run_id != unscoped_context.run_id for e in scoped_received)


# ---------------------------------------------------------------------------
# 18G: failure isolation across independent executions (EVT-FAIL-02)
# ---------------------------------------------------------------------------


def test_failure_in_one_execution_does_not_affect_a_sibling_execution():
    scope_a = EventScope()
    scope_b = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope_a.subscribe(received_a.append)
    scope_b.subscribe(received_b.append)

    context_a = ExecutionContext(event_scope=scope_a)
    context_b = ExecutionContext(event_scope=scope_b)

    with pytest.raises(ExecutionError):
        Sequential(Retriever(), FailingStage())("query-a", context=context_a)

    # B runs after A's failure and must complete normally, with its
    # events staying isolated to scope B.
    result_b = Sequential(Retriever(), Reranker())("query-b", context=context_b)
    assert result_b == ["doc-b", "doc-about-query-b"]

    run_ids_a = {context_a.run_id} | {e.run_id for e in received_a}
    run_ids_b = {context_b.run_id} | {e.run_id for e in received_b}
    assert run_ids_a.isdisjoint(run_ids_b)
    assert EventType.MODULE_FAILED in [e.type for e in received_a]
    assert EventType.MODULE_FAILED not in [e.type for e in received_b]


# ---------------------------------------------------------------------------
# 18G: concurrent execution-scope isolation (EVT-CONC-01/02/04/05)
#
# Repository audit (18G): EventScope/EventBus hold no lock, no
# threading/asyncio/contextvars import anywhere in events.py, context.py,
# or module.py -- delivery is a plain synchronous for-loop over a plain
# list. Two distinct EventScope instances share NO mutable state with
# each other by construction (scope_a._listeners and scope_b._listeners
# are different list objects, with no reference between them) -- this is
# a structural guarantee about ownership, independent of any claim about
# thread safety. This test proves that structural guarantee empirically,
# under real overlapping execution, rather than resting on the reasoning
# alone. It uses threading.Barrier for deterministic synchronization --
# never time.sleep -- so both executions provably overlap in wall-clock
# time. This says nothing about EventBus (see the global-bus test below,
# which is deliberately NOT framed as a thread-safety proof).
# ---------------------------------------------------------------------------


class _BarrieredRetriever(Module):
    """Blocks on a caller-supplied barrier before returning -- used to
    force two threads' executions to provably overlap in wall-clock
    time, deterministically, instead of relying on time.sleep."""

    def __init__(self, barrier: threading.Barrier) -> None:
        super().__init__()
        self._barrier = barrier

    def forward(self, query, *, context=None):
        self._barrier.wait(timeout=5)
        return [f"doc-about-{query}"]


def test_concurrent_executions_do_not_cross_event_scopes():
    barrier = threading.Barrier(2)
    retriever_a = _BarrieredRetriever(barrier)
    retriever_b = _BarrieredRetriever(barrier)

    scope_a = EventScope()
    scope_b = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope_a.subscribe(received_a.append)
    scope_b.subscribe(received_b.append)

    context_a = ExecutionContext(event_scope=scope_a)
    context_b = ExecutionContext(event_scope=scope_b)

    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def run_a() -> None:
        try:
            results["a"] = Sequential(retriever_a, Reranker())("query-a", context=context_a)
        except BaseException as exc:  # noqa: BLE001 -- surfaced via errors list, not swallowed
            errors.append(exc)

    def run_b() -> None:
        try:
            results["b"] = Sequential(retriever_b, Reranker())("query-b", context=context_b)
        except BaseException as exc:  # noqa: BLE001 -- surfaced via errors list, not swallowed
            errors.append(exc)

    thread_a = threading.Thread(target=run_a)
    thread_b = threading.Thread(target=run_b)
    thread_a.start()
    thread_b.start()
    thread_a.join(timeout=5)
    thread_b.join(timeout=5)

    assert not thread_a.is_alive()
    assert not thread_b.is_alive()
    assert errors == []
    assert results["a"] == ["doc-about-query-a"]
    assert results["b"] == ["doc-about-query-b"]

    assert received_a
    assert received_b

    run_ids_a = {context_a.run_id} | {e.run_id for e in received_a}
    run_ids_b = {context_b.run_id} | {e.run_id for e in received_b}
    assert run_ids_a.isdisjoint(run_ids_b)

    # every event delivered to scope A traces into A's own run-id graph,
    # and likewise for B -- not merely "each list is non-empty".
    assert all(e.run_id in run_ids_a for e in received_a)
    assert all(e.run_id in run_ids_b for e in received_b)

    # each execution's own event stream stays internally coherent
    # (STARTED before FINISHED for every module_name that finished).
    for received in (received_a, received_b):
        by_run: dict[str | None, list[EventType]] = {}
        for event in received:
            by_run.setdefault(event.run_id, []).append(event.type)
        for types in by_run.values():
            assert types[0] is EventType.MODULE_STARTED
            assert types[-1] in (EventType.MODULE_FINISHED, EventType.MODULE_FAILED)


def test_concurrent_executions_stay_isolated_across_repeated_runs():
    """Run the concurrent-isolation scenario several times in one test
    to catch accidental shared mutable state that a single run might
    not expose (EVT-CONC-06)."""
    for _ in range(20):
        barrier = threading.Barrier(2)

        scope_a = EventScope()
        scope_b = EventScope()
        received_a: list[Event] = []
        received_b: list[Event] = []
        scope_a.subscribe(received_a.append)
        scope_b.subscribe(received_b.append)

        context_a = ExecutionContext(event_scope=scope_a)
        context_b = ExecutionContext(event_scope=scope_b)

        thread_a = threading.Thread(
            target=_BarrieredRetriever(barrier), args=("qa",), kwargs={"context": context_a}
        )
        thread_b = threading.Thread(
            target=_BarrieredRetriever(barrier), args=("qb",), kwargs={"context": context_b}
        )
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)

        assert not thread_a.is_alive()
        assert not thread_b.is_alive()

        run_ids_a = {context_a.run_id}
        run_ids_b = {context_b.run_id}
        assert all(e.run_id in run_ids_a for e in received_a)
        assert all(e.run_id in run_ids_b for e in received_b)
        assert received_a and received_b


# ---------------------------------------------------------------------------
# 18G: the global EventBus's pre-existing, deferred concurrency gap
# (ADR-022 Q10). EventBus._listeners is a plain, unsynchronized list; no
# lock, no explicit synchronization primitive guards subscribe/
# unsubscribe/publish.
#
# IMPORTANT: this test observes the outcome of ONE particular scheduling
# of two threads on one particular interpreter (CPython). It is NOT
# proof of a thread-safety guarantee -- individual list operations being
# atomic under CPython's GIL does not make the compound
# "for listener in self._listeners: listener(event)" loop a specified,
# race-free protocol under concurrent subscribe/unsubscribe, under a
# raising listener, or under a future interpreter without CPython's GIL
# behavior. This test pins today's observed behavior on today's
# interpreter; it does not and cannot establish a contract. EventBus
# concurrent behavior remains explicitly UNGUARANTEED -- see ADR-022's
# Concurrency section and Deferred Risks (EVT-RACE-001).
# ---------------------------------------------------------------------------


def test_global_bus_current_concurrent_delivery_behavior_on_cpython():
    bus = event_bus()
    received: list[Event] = []
    lock = threading.Lock()

    def thread_safe_listener(event: Event) -> None:
        with lock:
            received.append(event)

    barrier = threading.Barrier(2)

    bus.subscribe(thread_safe_listener)
    try:
        context_a = ExecutionContext()
        context_b = ExecutionContext()

        thread_a = threading.Thread(
            target=_BarrieredRetriever(barrier), args=("qa",), kwargs={"context": context_a}
        )
        thread_b = threading.Thread(
            target=_BarrieredRetriever(barrier), args=("qb",), kwargs={"context": context_b}
        )
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=5)
        thread_b.join(timeout=5)

        assert not thread_a.is_alive()
        assert not thread_b.is_alive()
    finally:
        bus.unsubscribe(thread_safe_listener)

    # Under THIS run, on THIS interpreter, no listener registration was
    # lost and no event was dropped -- an observation about today's
    # CPython behavior, not a specified EventBus thread-safety contract.
    # See ADR-022 Concurrency / EVT-RACE-001: no guarantee is claimed.
    filtered = [e for e in received if e.run_id in (context_a.run_id, context_b.run_id)]
    assert len([e for e in filtered if e.run_id == context_a.run_id]) == 2
    assert len([e for e in filtered if e.run_id == context_b.run_id]) == 2


# ---------------------------------------------------------------------------
# ADR-023: listener-failure isolation through real Module.__call__/
# Sequential composition paths -- not just direct EventBus/EventScope
# unit tests. Confirms the precise, EMPIRICALLY VERIFIED (not assumed --
# this ADR's own drafting got it wrong twice before checking directly)
# claim from ADR-023's Non-goals: for all three event types
# (MODULE_STARTED, MODULE_FINISHED, MODULE_FAILED), a raising listener
# causes ListenerDeliveryError to propagate RAW, never wrapped as
# ExecutionError -- including MODULE_FAILED's publish calls, which sit
# lexically inside Module.__call__'s except block but are not thereby
# caught by it (an except clause only catches exceptions from its own
# try:, not from its own body).
# ---------------------------------------------------------------------------


def test_failing_listener_on_module_started_propagates_unwrapped():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        if event.type is EventType.MODULE_STARTED:
            raise RuntimeError("boom on start")

    scope.subscribe(failing_listener)
    context = ExecutionContext(event_scope=scope)

    with pytest.raises(ListenerDeliveryError):
        Retriever()("query", context=context)


def test_failing_listener_on_module_finished_propagates_unwrapped():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        if event.type is EventType.MODULE_FINISHED:
            raise RuntimeError("boom on finish")

    scope.subscribe(failing_listener)
    context = ExecutionContext(event_scope=scope)

    with pytest.raises(ListenerDeliveryError):
        Retriever()("query", context=context)


def test_failing_listener_on_module_failed_also_propagates_unwrapped():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        if event.type is EventType.MODULE_FAILED:
            raise RuntimeError("boom on failed")

    scope.subscribe(failing_listener)
    context = ExecutionContext(event_scope=scope)

    # Even though this publish() call is lexically inside
    # Module.__call__'s `except Exception as exc:` block, that clause
    # only catches exceptions from forward() (the block's own try:),
    # not exceptions raised by the block's own body -- so
    # ListenerDeliveryError propagates raw here too, exactly like the
    # other two event types. NOT wrapped as ExecutionError.
    with pytest.raises(ListenerDeliveryError):
        FailingStage()("query", context=context)


def test_listener_failure_isolation_through_sequential_composition():
    scope = EventScope()
    received: list[Event] = []

    def sometimes_failing(event: Event) -> None:
        received.append(event)
        if event.module_name == "Reranker" and event.type is EventType.MODULE_FINISHED:
            raise RuntimeError("reranker listener failed")

    scope.subscribe(sometimes_failing)
    context = ExecutionContext(event_scope=scope)
    pipeline = Sequential(Retriever(), Reranker())

    with pytest.raises(ExecutionError):
        pipeline("query", context=context)

    # despite the listener raising on Reranker's MODULE_FINISHED event,
    # every event up to and including that one was still recorded --
    # isolate-and-continue held even through real Sequential composition.
    module_names_seen = {e.module_name for e in received}
    assert "Retriever" in module_names_seen
    assert "Reranker" in module_names_seen
