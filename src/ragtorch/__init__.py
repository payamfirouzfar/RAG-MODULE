"""ragtorch: a framework kernel for building modular RAG systems.

Step 1 provided the core kernel — Module, RAGModule, Sequential,
configuration, errors, and events. Step 2 adds execution identity,
observability (traces, metrics, structured logs), and evaluation
primitives. No LLM, embedding, or vector-store integrations live
here; those are built on top of this foundation in later steps.
"""

from ragtorch.core import (
    ConfigurationError,
    Event,
    EventBus,
    EventType,
    ExecutionContext,
    ExecutionError,
    Module,
    ModuleError,
    RAGConfig,
    RAGModule,
    RAGTorchError,
    RegistryError,
    Run,
    RunStatus,
    Sequential,
    ValidationError,
    event_bus,
    new_run_id,
)

__version__ = "0.2.0"

__all__ = [
    "__version__",
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
