"""Contract test: the top-level public API surface must remain stable."""

from __future__ import annotations

import ragtorch


def test_public_exports_present():
    expected = {
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
        "__version__",
    }
    assert expected.issubset(set(ragtorch.__all__))


def test_version_is_a_string():
    assert isinstance(ragtorch.__version__, str)
