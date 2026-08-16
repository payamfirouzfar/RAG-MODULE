"""ragtorch: a framework kernel for building modular RAG systems.

Step 1 provided the core kernel — Module, RAGModule, Sequential,
configuration, errors, and events. Step 2 added execution identity,
observability (traces, metrics, structured logs), and evaluation
primitives. Step 3 added ExecutionEngine, which coordinates Run/Trace/
Metrics around a Module call as a guaranteed contract rather than a
convention every caller must re-derive. Step 4 propagates
ExecutionContext through nested Module execution (e.g. Sequential's
children), so composite RAG systems get correctly-parented execution
identity for each child without any global state. Step 6 adds
Component, a minimal structural protocol (name, component_type,
__call__) that Module already satisfies without inheriting from it,
so future components can be recognized by the framework without a
ragtorch dependency. Step 7 adds InputPort/OutputPort/is_compatible,
optional architecture metadata describing a component's input/output
boundary so two independent components can be checked for
compatibility without executing either. No LLM, embedding, or
vector-store integrations live here; those are built on top of this
foundation in later steps.
"""

from ragtorch.core import (
    Component,
    ConfigurationError,
    Event,
    EventBus,
    EventType,
    ExecutionContext,
    ExecutionEngine,
    ExecutionError,
    ExecutionResult,
    InputPort,
    MetricsCollector,
    MetricSummary,
    Module,
    ModuleError,
    ObservabilityLevel,
    OutputPort,
    RAGConfig,
    RAGModule,
    RAGTorchError,
    RegistryError,
    Run,
    RunStatus,
    Sequential,
    Span,
    Trace,
    ValidationError,
    event_bus,
    get_logger,
    is_compatible,
    is_sensitive_key,
    log_event,
    new_run_id,
    new_span_id,
    redact,
)

__version__ = "0.4.0"

__all__ = [
    "__version__",
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
