"""ragtorch: a framework kernel for building modular RAG systems.

Step 1 provides only the core kernel — Module, RAGModule, Sequential,
configuration, errors, and events. No LLM, embedding, or vector-store
integrations live here; those are built on top of this foundation in
later steps.
"""

from ragtorch.core import (
    ConfigurationError,
    Event,
    EventBus,
    EventType,
    ExecutionError,
    Module,
    ModuleError,
    RAGConfig,
    RAGModule,
    RAGTorchError,
    RegistryError,
    Sequential,
    ValidationError,
    event_bus,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
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
