from __future__ import annotations

import threading

import pytest

from ragtorch.core.context import ExecutionContext
from ragtorch.core.errors import ListenerDeliveryError
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
# ADR-023: listener-failure isolation supersedes ADR-022's EVT-FAILSTOP
# short-circuit contract -- a raising global-bus listener no longer
# prevents scope delivery; both destinations still fire, and failures
# from either are reported via ListenerDeliveryError rather than the
# raw listener exception propagating and stopping delivery.
# ---------------------------------------------------------------------------


def test_global_listener_failure_still_prevents_scope_delivery_through_module_call():
    """ADR-023 isolates listener failures WITHIN one EventBus/EventScope
    .publish() call, but Module.__call__'s dual-publish (ADR-022) is two
    separate, sequential, unwrapped statements: _bus.publish(started)
    then scope.publish(started). A raising global-bus listener now
    raises ListenerDeliveryError (not the raw listener exception), but
    that still prevents the second statement (scope.publish) from
    running -- Module.__call__ itself is explicitly untouched by
    ADR-023 (see its Non-goals). This is a real, named scope boundary,
    not an oversight: fixing the cross-call sequencing would be an
    ADR-022 change, out of scope here."""
    scope = EventScope()
    scoped_events: list[Event] = []
    scope.subscribe(scoped_events.append)

    def failing_listener(event: Event) -> None:
        raise RuntimeError("global listener failed")

    bus = event_bus()
    bus.subscribe(failing_listener)
    try:
        context = ExecutionContext(event_scope=scope)
        with pytest.raises(ListenerDeliveryError):
            ContextEcho()(1, context=context)
    finally:
        bus.unsubscribe(failing_listener)

    # unchanged from before ADR-023: Module.__call__'s dual-publish
    # sequencing means the scope never sees this event when the
    # global bus's own publish() call raises first.
    assert scoped_events == []


def test_event_scope_itself_isolates_from_a_failing_global_bus_listener():
    """Unlike the Module.__call__ dual-publish case above, calling
    EventScope.publish() directly (not through Module.__call__) is
    fully independent of the global EventBus -- the two were never
    coupled at that level. This isolates the claim: ADR-023's
    isolation guarantee holds for each publish() call in isolation;
    the Module.__call__ sequencing gap above is a separate, narrower,
    named limitation."""
    scope = EventScope()
    scoped_events: list[Event] = []
    scope.subscribe(scoped_events.append)

    event = Event(EventType.MODULE_STARTED, "x")
    scope.publish(event)  # no global bus involved at all

    assert scoped_events == [event]


def test_scope_listener_failure_raises_listener_delivery_error():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        raise RuntimeError("scope listener failed")

    scope.subscribe(failing_listener)
    context = ExecutionContext(event_scope=scope)

    with pytest.raises(ListenerDeliveryError, match="scope listener failed"):
        ContextEcho()(1, context=context)


def test_event_scope_isolates_listener_exceptions():
    scope = EventScope()

    def failing_listener(event: Event) -> None:
        raise RuntimeError("listener failed")

    scope.subscribe(failing_listener)

    with pytest.raises(ListenerDeliveryError, match="listener failed"):
        scope.publish(Event(EventType.MODULE_STARTED, "x"))


# ---------------------------------------------------------------------------
# ADR-023: listener-failure isolation contract (FAIL-ISO-*)
# Applied identically to both EventBus and EventScope (structurally
# identical publish() implementations) -- parametrized where practical.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_01_no_listener_raises_publish_returns_normally(bus_cls):
    bus = bus_cls()
    received: list[Event] = []
    bus.subscribe(received.append)

    event = Event(EventType.MODULE_STARTED, "x")
    bus.publish(event)  # must not raise

    assert received == [event]


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_02_one_listener_raises_others_still_run(bus_cls):
    bus = bus_cls()
    received: list[Event] = []

    def failing(event: Event) -> None:
        raise RuntimeError("boom")

    bus.subscribe(failing)
    bus.subscribe(received.append)

    with pytest.raises(ListenerDeliveryError) as exc_info:
        bus.publish(Event(EventType.MODULE_STARTED, "x"))

    assert received  # the non-raising listener still ran
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0][0] is failing
    assert isinstance(exc_info.value.failures[0][1], RuntimeError)


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_03_multiple_listeners_raise_all_recorded_in_order(bus_cls):
    bus = bus_cls()

    def failing_a(event: Event) -> None:
        raise ValueError("a")

    def failing_b(event: Event) -> None:
        raise TypeError("b")

    bus.subscribe(failing_a)
    bus.subscribe(failing_b)

    with pytest.raises(ListenerDeliveryError) as exc_info:
        bus.publish(Event(EventType.MODULE_STARTED, "x"))

    assert [listener for listener, _ in exc_info.value.failures] == [
        failing_a,
        failing_b,
    ]
    assert [type(exc) for _, exc in exc_info.value.failures] == [ValueError, TypeError]


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_04_later_listeners_side_effects_still_happen(bus_cls):
    bus = bus_cls()
    mutated: list[str] = []

    def failing(event: Event) -> None:
        raise RuntimeError("boom")

    def mutates(event: Event) -> None:
        mutated.append("ran")

    bus.subscribe(failing)
    bus.subscribe(mutates)

    with pytest.raises(ListenerDeliveryError):
        bus.publish(Event(EventType.MODULE_STARTED, "x"))

    assert mutated == ["ran"]


class _CustomBaseException(BaseException):
    pass


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_05_non_exception_base_exception_is_not_caught(bus_cls):
    bus = bus_cls()
    received: list[Event] = []

    def raises_base_exception(event: Event) -> None:
        raise _CustomBaseException("not an Exception subclass")

    def never_reached(event: Event) -> None:
        received.append(event)

    bus.subscribe(raises_base_exception)
    bus.subscribe(never_reached)

    with pytest.raises(_CustomBaseException):
        bus.publish(Event(EventType.MODULE_STARTED, "x"))

    # unlike Exception, a BaseException stops delivery immediately --
    # the listener after it never runs.
    assert received == []


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_06_unsubscribing_a_listener_during_publish_still_runs_it(bus_cls):
    bus = bus_cls()
    order: list[str] = []

    def a(event: Event) -> None:
        order.append("a")
        bus.unsubscribe(b)

    def b(event: Event) -> None:
        order.append("b")

    def c(event: Event) -> None:
        order.append("c")

    bus.subscribe(a)
    bus.subscribe(b)
    bus.subscribe(c)
    bus.publish(Event(EventType.MODULE_STARTED, "x"))

    # snapshot semantics (ADR-023): b was subscribed at the start of
    # this publish() call, so it still runs, unlike pre-ADR-023
    # live-iteration behavior which silently skipped it.
    assert order == ["a", "b", "c"]


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_07_subscribing_a_listener_during_publish_does_not_run_it_yet(bus_cls):
    bus = bus_cls()
    order: list[str] = []

    def late(event: Event) -> None:
        order.append("late")

    def a(event: Event) -> None:
        order.append("a")
        bus.subscribe(late)

    bus.subscribe(a)
    bus.publish(Event(EventType.MODULE_STARTED, "x"))
    assert order == ["a"]  # late was not invoked by this call

    order.clear()
    bus.publish(Event(EventType.MODULE_STARTED, "y"))
    assert order == ["a", "late"]  # only invoked starting next call


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_fail_iso_09_reentrant_publish_raises_clean_recursion_error(bus_cls):
    bus = bus_cls()

    def reenters(event: Event) -> None:
        bus.publish(Event(EventType.MODULE_FINISHED, "y"))

    bus.subscribe(reenters)

    with pytest.raises(RecursionError):
        bus.publish(Event(EventType.MODULE_STARTED, "x"))


# ---------------------------------------------------------------------------
# ADR-022: public API surface (API-01)
# ---------------------------------------------------------------------------


def test_event_scope_importable_from_core_and_root():
    from ragtorch import EventScope as RootEventScope
    from ragtorch.core import EventScope as CoreEventScope

    assert RootEventScope is EventScope
    assert CoreEventScope is EventScope


def test_listener_delivery_error_importable_from_core_and_root():
    from ragtorch import ListenerDeliveryError as RootLDE
    from ragtorch.core import ListenerDeliveryError as CoreLDE

    assert RootLDE is ListenerDeliveryError
    assert CoreLDE is ListenerDeliveryError


# ---------------------------------------------------------------------------
# Step 21: EVT-RACE-001 concurrency audit -- deterministic (threading.Barrier,
# never time.sleep), permanent characterization tests, not a proof of a
# thread-safety guarantee.
#
# Repository audit + adversarial review (21A-21C) found:
#   - Zero memory-corruption/crash hazards under aggressive concurrent
#     subscribe/unsubscribe/publish churn (CPython's GIL protects every
#     individual list operation; Step 20's publish()-time snapshot
#     already isolates each call from concurrent mutation).
#   - The one real finding -- concurrent double-unsubscribe() of the
#     SAME listener from two threads races to a ValueError in the
#     losing thread -- is PRE-EXISTING, SINGLE-THREADED behavior:
#     unsubscribe() on an already-removed listener already raises
#     ValueError with zero threads involved. Concurrency does not
#     introduce a new failure mode here, it only makes an existing,
#     already-undocumented single-threaded contract question
#     (is unsubscribe() idempotent? no) reachable non-deterministically.
#
# Conclusion: no ADR-024, no synchronization primitive added -- the
# evidence does not support it, matching SequentialExecutor's own
# existing precedent (ADR-018) of explicitly documenting
# "thread-safety... not claimed here" rather than adding a lock nothing
# demonstrates is needed. See evaluation/step21-evaluation.md.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_concurrent_subscribe_does_not_corrupt_or_lose_registrations(bus_cls):
    bus = bus_cls()
    barrier = threading.Barrier(2)
    iterations = 500

    def subscribe_many():
        barrier.wait(timeout=5)
        for _ in range(iterations):
            bus.subscribe(lambda e: None)

    threads = [threading.Thread(target=subscribe_many) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive()

    assert len(bus._listeners) == iterations * 2


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_concurrent_publish_delivers_every_event_no_loss_no_duplication(bus_cls):
    bus = bus_cls()
    lock = threading.Lock()
    count = [0]

    def listener(event: Event) -> None:
        with lock:
            count[0] += 1

    bus.subscribe(listener)
    barrier = threading.Barrier(4)
    publishes_per_thread = 250

    def publish_many():
        barrier.wait(timeout=5)
        for _ in range(publishes_per_thread):
            bus.publish(Event(EventType.MODULE_STARTED, "x"))

    threads = [threading.Thread(target=publish_many) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
        assert not t.is_alive()

    assert count[0] == publishes_per_thread * 4


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_concurrent_subscribe_and_publish_does_not_crash(bus_cls):
    """publish()'s snapshot-before-iterating (ADR-023) is exercised
    concurrently with subscribe() churn -- no crash, no corruption.
    Not a claim that publish() sees a specified set of listeners under
    concurrent mutation, only that nothing breaks."""
    bus = bus_cls()

    def listener(event: Event) -> None:
        pass

    barrier = threading.Barrier(2)
    stop = threading.Event()
    errors: list[BaseException] = []

    # Capped, not unbounded: an unbounded churn_subscribe loop makes
    # publish()'s cost grow with however many listeners accumulated by
    # the time each publish() runs, which is CI-runner-speed-dependent
    # and can blow past any fixed join() timeout on a slow/shared
    # runner (this exact failure mode was caught by real CI, not
    # invented) -- the point of this test is "does concurrent mutation
    # crash publish()", not "how many listeners can we accumulate", so
    # capping the growth preserves the test's actual intent while
    # making its runtime bounded and CI-stable.
    max_extra_listeners = 2_000

    def churn_subscribe():
        barrier.wait(timeout=5)
        added = 0
        while not stop.is_set() and added < max_extra_listeners:
            bus.subscribe(listener)
            added += 1

    def churn_publish():
        barrier.wait(timeout=5)
        try:
            for _ in range(2_000):
                bus.publish(Event(EventType.MODULE_STARTED, "x"))
        except BaseException as exc:  # noqa: BLE001 -- surfaced via errors, not swallowed
            errors.append(exc)

    subscribe_thread = threading.Thread(target=churn_subscribe)
    publish_thread = threading.Thread(target=churn_publish)
    subscribe_thread.start()
    publish_thread.start()
    publish_thread.join(timeout=60)
    stop.set()
    subscribe_thread.join(timeout=10)

    assert not publish_thread.is_alive()
    assert not subscribe_thread.is_alive()
    assert errors == []


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_concurrent_unsubscribe_of_the_same_listener_can_race_to_valueerror(bus_cls):
    """The one real finding from Step 21's audit: two threads racing to
    unsubscribe() the SAME listener can have the losing thread raise
    ValueError. This is deterministically reproducible (not a rare
    timing accident) via threading.Barrier -- and it is PRE-EXISTING,
    single-threaded behavior (see the paired single-threaded test
    below), not a new concurrency-specific defect. Documented here as
    a permanent characterization, not fixed -- unsubscribe() is not
    idempotent, single- or multi-threaded, and no evidence currently
    justifies changing that."""
    bus = bus_cls()

    def listener(event: Event) -> None:
        pass

    bus.subscribe(listener)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    outcomes_lock = threading.Lock()

    def unsubscribe_once():
        barrier.wait(timeout=5)
        try:
            bus.unsubscribe(listener)
            outcome = "ok"
        except ValueError:
            outcome = "ValueError"
        with outcomes_lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=unsubscribe_once) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()

    # exactly one thread wins (removes it), the other loses (ValueError)
    assert sorted(outcomes) == ["ValueError", "ok"]


@pytest.mark.parametrize("bus_cls", [EventBus, EventScope])
def test_double_unsubscribe_already_raises_single_threaded(bus_cls):
    """Pins the pre-existing, single-threaded root cause of the
    concurrent finding above: unsubscribe() on an already-removed
    listener raises ValueError with zero threads involved. Concurrency
    doesn't introduce this -- it only makes it reachable
    non-deterministically."""
    bus = bus_cls()

    def listener(event: Event) -> None:
        pass

    bus.subscribe(listener)
    bus.unsubscribe(listener)

    with pytest.raises(ValueError):
        bus.unsubscribe(listener)
