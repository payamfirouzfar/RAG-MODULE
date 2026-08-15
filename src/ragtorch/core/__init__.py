"""Core kernel: framework-agnostic abstractions with no vendor dependencies."""

from ragtorch.core.config import RAGConfig
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
from ragtorch.core.sequential import Sequential

__all__ = [
    "Module",
    "RAGModule",
    "Sequential",
    "RAGConfig",
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
