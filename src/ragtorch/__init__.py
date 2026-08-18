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
ArchitectureNode.id. Step 13 adds ExecutionPlan/ExecutionStep/plan():
plan(graph) derives a deterministic topological ordering from a valid
CompositionGraph using Kahn's algorithm with an explicit FIFO ready
queue. ExecutionPlan contains no runtime objects and does not retain
the source graph — deriving a plan is a pure, one-way transformation.
No executor, no ExecutionEngine integration, no parallel/async
execution yet — see ADR-017. Step 14 adds the executor: Executor/
StepHandler (Protocols) and SequentialExecutor, which runs an
ExecutionPlan's steps in order via a caller-supplied StepHandler,
threading prior results forward through an immutable
StepExecutionContext snapshot and returning a StepExecutionResult.
Provider-independent by construction -- the executor never resolves a
step to a Component itself; that is entirely the handler's
responsibility. No ExecutionEngine integration, no async/parallel/
distributed execution, no retries or timeouts yet — see ADR-018.
StepExecutionContext/StepExecutionResult are deliberately not named
ExecutionContext/ExecutionResult -- those names are already used by
unrelated types (run identity/metadata, and the ExecutionEngine's
Run/Trace/Metrics bundle, respectively). Step 15 adds
ExecutionEngine.execute_plan(), extending the same Run/Trace/Metrics
lifecycle guarantee execute() gives a single Module call to an entire
ExecutionPlan, with plan iteration fully delegated to an Executor --
see ADR-019. Step 16 adds Block: a Module subclass that structurally
satisfies Component and owns a CompositionGraph, delegating all
execution to the existing plan()/Executor/ExecutionEngine.execute_plan
chain -- no second execution system, no runtime change required to
support it, since GraphNode.component was already accepted
structurally-typed and unchecked. Block requires an explicit
input_node/output_node pair (no first/last-node inference) and exactly
one dependency per non-entry node; multi-root/multi-sink/
multi-dependency Block semantics are explicit future work -- see
ADR-020. Serialization remains future work. No LLM, embedding, or
vector-store integrations live here; those are built on top of this
foundation in later steps.
"""

from importlib import metadata as _metadata

from ragtorch.core import (
    ArchitectureChild,
    ArchitectureNode,
    ArchitectureSnapshot,
    Block,
    Component,
    CompositionGraph,
    ConfigurationError,
    Connection,
    Event,
    EventBus,
    EventScope,
    EventType,
    ExecutionContext,
    ExecutionEngine,
    ExecutionError,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    Executor,
    GraphNode,
    InputPort,
    ListenerDeliveryError,
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
    SequentialExecutor,
    Span,
    StepExecutionContext,
    StepExecutionResult,
    StepHandler,
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
    plan,
    redact,
    snapshot,
    validate_snapshot,
)

try:
    # The installed *distribution* name is "ragmodel" (pyproject.toml's
    # `name` field / PyPI project name), even though the importable
    # package remains "ragtorch" -- these are allowed to differ, and
    # importlib.metadata.version() must be queried by the distribution
    # name, not the import name, or it raises PackageNotFoundError even
    # on a correctly installed package.
    __version__ = _metadata.version("ragmodel")
except _metadata.PackageNotFoundError:
    # Only reachable when ragtorch is imported from source without being
    # installed at all (neither editable nor a real install) -- every
    # supported install path (pip install -e, wheel install) registers
    # package metadata, so this is not expected in normal use.
    __version__ = "0.0.0+unknown"

__all__ = [
    "__version__",
    "Block",
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
    "ExecutionPlan",
    "ExecutionStep",
    "plan",
    "Executor",
    "SequentialExecutor",
    "StepHandler",
    "StepExecutionContext",
    "StepExecutionResult",
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
    "ListenerDeliveryError",
    "Event",
    "EventType",
    "EventBus",
    "EventScope",
    "event_bus",
]
