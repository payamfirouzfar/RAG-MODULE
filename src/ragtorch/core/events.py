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
