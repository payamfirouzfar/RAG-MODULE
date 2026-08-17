"""Framework-level exception hierarchy.

All exceptions raised by ragtorch's core inherit from RAGTorchError so
callers can catch the whole family with a single except clause.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ragtorch.core.events import Event, EventListener


class RAGTorchError(Exception):
    """Base class for all ragtorch exceptions."""


class ConfigurationError(RAGTorchError):
    """Raised when configuration is invalid or inconsistent."""


class ModuleError(RAGTorchError):
    """Raised for generic module-related failures."""


class ExecutionError(RAGTorchError):
    """Raised when execution of a module or pipeline fails."""


class RegistryError(RAGTorchError):
    """Raised when module registration is invalid (e.g. duplicate name)."""


class ValidationError(RAGTorchError):
    """Raised when input/output validation fails."""


class ListenerDeliveryError(RAGTorchError):
    """One or more listeners raised during EventBus/EventScope.publish().

    Every listener that was subscribed at the start of publish() was
    still invoked -- a raising listener never prevents delivery to
    listeners after it (ADR-023). ``failures`` holds every
    (listener, exception) pair, in delivery order. The original event
    is available as ``event``.
    """

    def __init__(
        self,
        event: Event,
        failures: tuple[tuple[EventListener, Exception], ...],
    ) -> None:
        self.event = event
        self.failures = failures
        summary = ", ".join(
            f"{getattr(listener, '__name__', repr(listener))}: {type(exc).__name__}: {exc}"
            for listener, exc in failures
        )
        super().__init__(
            f"{len(failures)} listener(s) raised while publishing "
            f"{event.type.value} for '{event.module_name}': {summary}"
        )
