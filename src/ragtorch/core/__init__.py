"""Core kernel: framework-agnostic abstractions with no vendor dependencies."""

from ragtorch.core.architecture import validate_snapshot
from ragtorch.core.component import Component
from ragtorch.core.config import RAGConfig
from ragtorch.core.context import ExecutionContext, new_run_id
from ragtorch.core.engine import ExecutionEngine, ExecutionResult, ObservabilityLevel
from ragtorch.core.errors import (
    ConfigurationError,
    ExecutionError,
    ModuleError,
    RAGTorchError,
    RegistryError,
    ValidationError,
)
from ragtorch.core.events import Event, EventBus, EventType
from ragtorch.core.inspection import (
    ArchitectureChild,
    ArchitectureNode,
    ArchitectureSnapshot,
    snapshot,
)
from ragtorch.core.logging import get_logger, is_sensitive_key, log_event, redact
from ragtorch.core.metrics import MetricsCollector, MetricSummary
from ragtorch.core.module import Module, RAGModule, event_bus
from ragtorch.core.ports import InputPort, OutputPort, check_connection, is_compatible
from ragtorch.core.run import Run, RunStatus
from ragtorch.core.sequential import Sequential
from ragtorch.core.trace import Span, Trace, new_span_id

__all__ = [
    "Component",
    "Module",
    "RAGModule",
    "Sequential",
    "RAGConfig",
    "ExecutionContext",
    "new_run_id",
    "Run",
    "RunStatus",
    "Trace",
    "Span",
    "new_span_id",
    "MetricsCollector",
    "MetricSummary",
    "InputPort",
    "OutputPort",
    "is_compatible",
    "check_connection",
    "ArchitectureNode",
    "ArchitectureChild",
    "ArchitectureSnapshot",
    "snapshot",
    "validate_snapshot",
    "ExecutionEngine",
    "ExecutionResult",
    "ObservabilityLevel",
    "get_logger",
    "log_event",
    "redact",
    "is_sensitive_key",
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
