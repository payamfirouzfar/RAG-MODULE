"""Core kernel: framework-agnostic abstractions with no vendor dependencies."""

from ragtorch.core.config import RAGConfig
from ragtorch.core.context import ExecutionContext, new_run_id
from ragtorch.core.errors import (
    ConfigurationError,
    ExecutionError,
    ModuleError,
    RAGTorchError,
    RegistryError,
    ValidationError,
)
from ragtorch.core.events import Event, EventBus, EventType
from ragtorch.core.module import Module, RAGModule, event_bus
from ragtorch.core.run import Run, RunStatus
from ragtorch.core.sequential import Sequential

__all__ = [
    "Module",
    "RAGModule",
    "Sequential",
    "RAGConfig",
    "ExecutionContext",
    "new_run_id",
    "Run",
    "RunStatus",
    "RAGTorchError",
    "ConfigurationError",
    "ModuleError",
    "ExecutionError",
    "RegistryError",
    "ValidationError",
    "Event",
    "EventType",
    "EventBus",
    "event_bus",
]
