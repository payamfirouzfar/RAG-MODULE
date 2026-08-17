"""Lightweight, vendor-agnostic event system for observability.

Events carry correlation identity when a Module is executed with an
ExecutionContext. Delivery remains synchronous and vendor-neutral.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ragtorch.core.errors import ListenerDeliveryError

logger = logging.getLogger("ragtorch")


class EventType(Enum):
    MODULE_STARTED = "module_started"
    MODULE_FINISHED = "module_finished"
    MODULE_FAILED = "module_failed"


@dataclass(frozen=True)
class Event:
    type: EventType
    module_name: str
    timestamp: float = field(default_factory=time.monotonic)
    payload: dict[str, Any] = field(default_factory=dict)
    run_id: str | None = None
    parent_run_id: str | None = None


EventListener = Callable[[Event], None]


class EventBus:
    """Synchronous publish/subscribe event bus."""

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        self._listeners.remove(listener)

    def publish(self, event: Event) -> None:
        """Deliver ``event`` to every subscribed listener.

        Every listener subscribed at the start of this call is
        invoked, even if an earlier listener raised (ADR-023) -- a
        snapshot of the listener list is taken before iteration
        begins, so mutation during delivery (subscribe/unsubscribe
        from within a listener) does not affect which listeners this
        call reaches. If any listener raised, ``ListenerDeliveryError``
        is raised after every listener has run, carrying every
        failure. If no listener raised, ``publish()`` returns normally.
        """
        failures: list[tuple[EventListener, Exception]] = []
        for listener in tuple(self._listeners):
            try:
                listener(event)
            except RecursionError:
                # Reentrant publish() (a listener calling publish()
                # again on the same bus) is out of scope for this
                # isolation contract (ADR-023, EVT-REENTRANT-001) --
                # re-raise immediately rather than wrapping it in
                # ListenerDeliveryError, which would otherwise nest
                # once per recursive level and obscure the original
                # RecursionError entirely.
                raise
            except Exception as exc:  # noqa: BLE001 -- isolated per ADR-023, not swallowed
                failures.append((listener, exc))
        logger.debug(
            "event: %s module=%s run_id=%s",
            event.type.value,
            event.module_name,
            event.run_id,
        )
        if failures:
            raise ListenerDeliveryError(event, tuple(failures))


class EventScope:
    """Execution-scoped event delivery (ADR-022).

    Distinct from the global, process-wide EventBus (event_bus()). A
    caller constructs an EventScope, subscribes listeners to it, and
    passes it via ExecutionContext(event_scope=...) to observe only
    that execution's (and its nested children's) events, without
    affecting or being affected by the global bus.

    Structurally identical to EventBus and consumes the same
    EventListener callable, but is a distinct type, not a subclass, so
    the two are never interchangeable by accident. Not thread-safe --
    the publish()-time snapshot (ADR-023) is not a synchronization
    primitive, it only protects against mutate-during-this-call side
    effects, not concurrent access from multiple threads. There is no
    module-level default instance, no contextvars binding, and no
    thread-local singleton -- an EventScope exists only where a caller
    explicitly constructs one.
    """

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        self._listeners.remove(listener)

    def publish(self, event: Event) -> None:
        """Deliver ``event`` to every subscribed listener.

        See EventBus.publish -- identical isolate-and-continue,
        snapshot, and ListenerDeliveryError semantics (ADR-023).
        """
        failures: list[tuple[EventListener, Exception]] = []
        for listener in tuple(self._listeners):
            try:
                listener(event)
            except RecursionError:
                # See EventBus.publish -- re-raise immediately rather
                # than wrapping in ListenerDeliveryError (ADR-023,
                # EVT-REENTRANT-001).
                raise
            except Exception as exc:  # noqa: BLE001 -- isolated per ADR-023, not swallowed
                failures.append((listener, exc))
        if failures:
            raise ListenerDeliveryError(event, tuple(failures))
