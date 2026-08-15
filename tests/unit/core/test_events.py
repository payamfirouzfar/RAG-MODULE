from __future__ import annotations

from ragtorch.core.context import ExecutionContext
from ragtorch.core.events import Event, EventBus, EventType
from ragtorch.core.module import Module, event_bus


class Echo(Module):
    def forward(self, input):
        return input


class ContextEcho(Module):
    def forward(self, input, *, context=None):
        return context.run_id


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
