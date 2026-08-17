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
        for listener in self._listeners:
            listener(event)
        logger.debug(
            "event: %s module=%s run_id=%s",
            event.type.value,
            event.module_name,
            event.run_id,
        )


class EventScope:
    """Execution-scoped event delivery (ADR-022).

    Distinct from the global, process-wide EventBus (event_bus()). A
    caller constructs an EventScope, subscribes listeners to it, and
    passes it via ExecutionContext(event_scope=...) to observe only
    that execution's (and its nested children's) events, without
    affecting or being affected by the global bus.

    Structurally identical to EventBus and consumes the same
    EventListener callable, but is a distinct type, not a subclass, so
    the two are never interchangeable by accident. Not thread-safe; a
    raising listener propagates from publish() unmodified -- both
    match EventBus's existing, unmodified behavior exactly. There is
    no module-level default instance, no contextvars binding, and no
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
        for listener in self._listeners:
            listener(event)
