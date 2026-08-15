from __future__ import annotations

from ragtorch.core.events import Event, EventBus, EventType
from ragtorch.core.module import Module, event_bus


class Echo(Module):
    def forward(self, input):
        return input


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
