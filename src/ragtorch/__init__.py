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
compatibility without executing either. Step 8 adds
ArchitectureSnapshot: a canonical, immutable description of a Module
tree (nodes + parent/child structure), built by walking the tree
exactly once. Module.inspect() now renders text from this snapshot
internally rather than an independent tree walk, keeping its output
unchanged. Step 9 adds validate_snapshot(), which checks that an
ArchitectureSnapshot is a well-formed, non-empty rooted tree (unique
ids, no dangling references, at most one parent per node, exactly one
root, full reachability) and raises ValidationError with a specific
message on the first violation found, or returns None. Step 10 adds
check_connection(), a raising precondition wrapper over
is_compatible(): "ask" (is_compatible, bool) vs. "enforce"
(check_connection, raises ValidationError). It does not integrate with
ArchitectureSnapshot/validate_snapshot() — that remains future work for
a composition/Block layer. Step 11 adds Connection: a frozen value
type persisting a single, directed, validated data-flow edge
(source_node_id, source_port) -> (target_node_id, target_port),
delegating compatibility checking to check_connection() rather than
duplicating it. Fan-out/fan-in cardinality, cycles, a graph/Block
aggregate, execution order, and serialization remain explicit future
work — see ADR-015. Step 12 adds CompositionGraph/GraphNode: an
immutable, validated collection of nodes and Connections, enforcing
unique node ids, referential integrity, no duplicate connections,
fan-in <= 1 per input port (fan-out unrestricted), and acyclicity.
GraphNode.id is graph-local identity, independent of
ArchitectureNode.id. No Block, execution planning, or serialization
yet — see ADR-016. No LLM, embedding, or vector-store integrations
live here; those are built on top of this foundation in later steps.
"""

from ragtorch.core import (
    ArchitectureChild,
    ArchitectureNode,
    ArchitectureSnapshot,
    Component,
    CompositionGraph,
    ConfigurationError,
    Connection,
    Event,
    EventBus,
    EventType,
    ExecutionContext,
    ExecutionEngine,
    ExecutionError,
    ExecutionResult,
    GraphNode,
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
    check_connection,
    event_bus,
    get_logger,
    is_compatible,
    is_sensitive_key,
    log_event,
    new_run_id,
    new_span_id,
    redact,
    snapshot,
    validate_snapshot,
)

__version__ = "0.4.0"

__all__ = [
    "__version__",
    "Component",
    "CompositionGraph",
    "GraphNode",
    "Connection",
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
