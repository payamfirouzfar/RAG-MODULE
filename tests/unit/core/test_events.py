from __future__ import annotations

import threading

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.events import Event, EventBus, EventScope, EventType
from ragtorch.core.module import Module, event_bus
from ragtorch.core.sequential import Sequential


class Echo(Module):
    def forward(self, input):
        return input


class ContextEcho(Module):
    def forward(self, input, *, context=None):
        return context.run_id


class Failing(Module):
    def forward(self, input, *, context=None):
        raise RuntimeError("boom")


def test_event_bus_publishes_to_subscribers():
    bus = EventBus()
    received = []
    bus.subscribe(received.append)
    bus.publish(Event(EventType.MODULE_STARTED, "x"))
    assert len(received) == 1
    assert received[0].type is EventType.MODULE_STARTED


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    received = []
    listener = received.append
    bus.subscribe(listener)
    bus.unsubscribe(listener)
    bus.publish(Event(EventType.MODULE_STARTED, "x"))
    assert received == []


def test_module_call_emits_started_and_finished_events():
    received: list[Event] = []

    def listener(event: Event) -> None:
        received.append(event)

    bus = event_bus()
    bus.subscribe(listener)
    try:
        Echo()(1)
    finally:
        bus.unsubscribe(listener)

    types = [e.type for e in received if e.module_name == "Echo"]
    assert EventType.MODULE_STARTED in types
    assert EventType.MODULE_FINISHED in types
    assert all(e.run_id is None for e in received if e.module_name == "Echo")


def test_module_events_carry_execution_identity_when_context_is_supplied():
    received: list[Event] = []

    def listener(event: Event) -> None:
        received.append(event)

    context = ExecutionContext()
    bus = event_bus()
    bus.subscribe(listener)
    try:
        ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(listener)

    events = [e for e in received if e.module_name == "ContextEcho"]
    assert [e.type for e in events] == [EventType.MODULE_STARTED, EventType.MODULE_FINISHED]
    assert all(e.run_id == context.run_id for e in events)
    assert all(e.parent_run_id == context.parent_run_id for e in events)


def test_nested_context_events_remain_distinguishable():
    received: list[Event] = []

    def listener(event: Event) -> None:
        received.append(event)

    parent = ExecutionContext()
    child = parent.child(step="retriever")
    bus = event_bus()
    bus.subscribe(listener)
    try:
        ContextEcho()(1, context=parent)
        ContextEcho()(2, context=child)
    finally:
        bus.unsubscribe(listener)

    events = [e for e in received if e.module_name == "ContextEcho"]
    run_ids = {e.run_id for e in events}
    assert run_ids == {parent.run_id, child.run_id}
    child_events = [e for e in events if e.run_id == child.run_id]
    assert all(e.parent_run_id == parent.run_id for e in child_events)


# ---------------------------------------------------------------------------
# ADR-022: EventScope primitive (EVT-01)
# ---------------------------------------------------------------------------


def test_event_scope_publishes_to_subscriber():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    event = Event(EventType.MODULE_STARTED, "x")
    scope.publish(event)

    assert received == [event]


def test_event_scope_unsubscribe_stops_delivery():
    scope = EventScope()
    received: list[Event] = []
    listener = received.append
    scope.subscribe(listener)
    scope.unsubscribe(listener)

    scope.publish(Event(EventType.MODULE_STARTED, "x"))

    assert received == []


def test_event_scope_can_have_multiple_subscribers():
    scope = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope.subscribe(received_a.append)
    scope.subscribe(received_b.append)

    event = Event(EventType.MODULE_STARTED, "x")
    scope.publish(event)

    assert received_a == [event]
    assert received_b == [event]


# ---------------------------------------------------------------------------
# ADR-022: no-context / no-scope compatibility (EVT-NOCTX-01/02)
# ---------------------------------------------------------------------------


def test_module_without_context_remains_global_only():
    received: list[Event] = []
    bus = event_bus()
    bus.subscribe(received.append)
    try:
        Echo()(1)
    finally:
        bus.unsubscribe(received.append)

    events = [e for e in received if e.module_name == "Echo"]
    assert events
    assert all(e.run_id is None for e in events)


def test_context_without_event_scope_remains_global_only():
    context = ExecutionContext()
    assert context.event_scope is None

    received: list[Event] = []
    bus = event_bus()
    bus.subscribe(received.append)
    try:
        ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(received.append)

    events = [e for e in received if e.module_name == "ContextEcho"]
    assert events
    assert all(e.run_id == context.run_id for e in events)


# ---------------------------------------------------------------------------
# ADR-022: dual delivery (EVT-03)
# ---------------------------------------------------------------------------


def test_scoped_module_publishes_to_global_bus_and_scope():
    scope = EventScope()
    global_events: list[Event] = []
    scoped_events: list[Event] = []

    bus = event_bus()
    bus.subscribe(global_events.append)
    scope.subscribe(scoped_events.append)
    try:
        context = ExecutionContext(event_scope=scope)
        ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(global_events.append)

    global_filtered = [e for e in global_events if e.module_name == "ContextEcho"]
    scoped_filtered = [e for e in scoped_events if e.module_name == "ContextEcho"]

    assert [e.type for e in global_filtered] == [
        EventType.MODULE_STARTED,
        EventType.MODULE_FINISHED,
    ]
    assert global_filtered == scoped_filtered  # same Event objects, both destinations


# ---------------------------------------------------------------------------
# ADR-022: child() preserves event_scope identity (EVT-CHILD)
# ---------------------------------------------------------------------------


def test_child_preserves_event_scope_identity():
    scope = EventScope()
    parent = ExecutionContext(event_scope=scope)

    child = parent.child()

    assert child.event_scope is scope
    assert child.run_id != parent.run_id
    assert child.parent_run_id == parent.run_id


def test_child_without_event_scope_stays_none():
    parent = ExecutionContext()
    child = parent.child()
    assert child.event_scope is None


# ---------------------------------------------------------------------------
# ADR-022: nested delivery (EVT-05)
# ---------------------------------------------------------------------------


def test_scope_receives_nested_execution_events():
    scope = EventScope()
    received: list[Event] = []
    scope.subscribe(received.append)

    context = ExecutionContext(event_scope=scope)
    Sequential(Echo(), Echo())(1, context=context)

    module_names = {e.module_name for e in received}
    assert "Sequential" in module_names
    assert "Echo" in module_names

    run_ids = {e.run_id for e in received}
    assert context.run_id in run_ids
    # every non-root event's parent_run_id traces back into this tree
    root_and_children = run_ids
    assert all(e.parent_run_id is None or e.parent_run_id in root_and_children for e in received)


# ---------------------------------------------------------------------------
# ADR-022: sibling isolation (EVT-06) -- the central regression test
# ---------------------------------------------------------------------------


def test_scope_isolated_between_independent_executions():
    scope_a = EventScope()
    scope_b = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope_a.subscribe(received_a.append)
    scope_b.subscribe(received_b.append)

    context_a = ExecutionContext(event_scope=scope_a)
    context_b = ExecutionContext(event_scope=scope_b)

    tree_a = Sequential(Echo(), Echo())
    tree_b = Sequential(Echo(), Echo())

    tree_a(1, context=context_a)
    tree_b(2, context=context_b)

    assert received_a
    assert received_b

    run_ids_a = {context_a.run_id} | {e.run_id for e in received_a}
    run_ids_b = {context_b.run_id} | {e.run_id for e in received_b}
    assert run_ids_a.isdisjoint(run_ids_b)

    # every event delivered to scope A actually belongs to tree A's
    # run-id graph, and likewise for B -- not merely "non-empty"
    assert all(e.run_id in run_ids_a for e in received_a)
    assert all(e.run_id in run_ids_b for e in received_b)


def test_shared_scope_receives_both_trees_events():
    """Sharing one EventScope across unrelated executions is explicit,
    caller-chosen behavior (ADR-022 Q8) -- not isolation by accident."""
    shared_scope = EventScope()
    received: list[Event] = []
    shared_scope.subscribe(received.append)

    context_a = ExecutionContext(event_scope=shared_scope)
    context_b = ExecutionContext(event_scope=shared_scope)

    Echo()(1, context=context_a)
    Echo()(2, context=context_b)

    run_ids = {e.run_id for e in received}
    assert context_a.run_id in run_ids
    assert context_b.run_id in run_ids


# ---------------------------------------------------------------------------
# ADR-022: concurrent isolation (EVT-07) -- deterministic synchronization
# ---------------------------------------------------------------------------


def test_scope_isolated_under_concurrent_execution():
    scope_a = EventScope()
    scope_b = EventScope()
    received_a: list[Event] = []
    received_b: list[Event] = []
    scope_a.subscribe(received_a.append)
    scope_b.subscribe(received_b.append)

    context_a = ExecutionContext(event_scope=scope_a)
    context_b = ExecutionContext(event_scope=scope_b)

    barrier = threading.Barrier(2)

    class Barriered(Module):
        def forward(self, input, *, context=None):
            barrier.wait(timeout=5)
            return input

    def run_a() -> None:
        Barriered()(1, context=context_a)

    def run_b() -> None:
        Barriered()(2, context=context_b)

    thread_a = threading.Thread(target=run_a)
    thread_b = threading.Thread(target=run_b)
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
    assert received_a
    assert received_b


# ---------------------------------------------------------------------------
# ADR-022: delivery ordering is not part of the public contract (EVT-ORDER)
# ---------------------------------------------------------------------------


def test_dual_delivery_does_not_assert_ordering():
    scope = EventScope()
    global_events: list[Event] = []
    scoped_events: list[Event] = []
    bus = event_bus()
    bus.subscribe(global_events.append)
    scope.subscribe(scoped_events.append)
    try:
        context = ExecutionContext(event_scope=scope)
        ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(global_events.append)

    global_filtered = [e for e in global_events if e.module_name == "ContextEcho"]
    scoped_filtered = [e for e in scoped_events if e.module_name == "ContextEcho"]

    # Both destinations receive every event -- membership, not ordering.
    for event in global_filtered:
        assert event in scoped_filtered
    for event in scoped_filtered:
        assert event in global_filtered


# ---------------------------------------------------------------------------
# ADR-022: failure short-circuits subsequent delivery (EVT-FAILSTOP)
# ---------------------------------------------------------------------------


def test_global_listener_failure_prevents_scope_delivery():
    scope = EventScope()
    scoped_events: list[Event] = []
    scope.subscribe(scoped_events.append)

    def failing_listener(event: Event) -> None:
        raise RuntimeError("global listener failed")

    bus = event_bus()
    bus.subscribe(failing_listener)
    try:
        context = ExecutionContext(event_scope=scope)
        with pytest.raises(RuntimeError, match="global listener failed"):
            ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(failing_listener)

    assert scoped_events == []


def test_scope_listener_failure_propagates():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        raise RuntimeError("scope listener failed")

    scope.subscribe(failing_listener)
    context = ExecutionContext(event_scope=scope)

    with pytest.raises(RuntimeError, match="scope listener failed"):
        ContextEcho()(1, context=context)


def test_event_scope_preserves_listener_exception_behavior():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        raise RuntimeError("listener failed")

    scope.subscribe(failing_listener)

    with pytest.raises(RuntimeError, match="listener failed"):
        scope.publish(Event(EventType.MODULE_STARTED, "x"))


# ---------------------------------------------------------------------------
# ADR-022: public API surface (API-01)
# ---------------------------------------------------------------------------


def test_event_scope_importable_from_core_and_root():
    from ragtorch import EventScope as RootEventScope
    from ragtorch.core import EventScope as CoreEventScope

    assert RootEventScope is EventScope
    assert CoreEventScope is EventScope
