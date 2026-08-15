"""Contract test: the top-level public API surface must remain stable."""

from __future__ import annotations

import ragtorch


def test_public_exports_present():
    expected = {
        "Module",
        "RAGModule",
        "Sequential",
        "RAGConfig",
        "ExecutionContext",
        "new_run_id",
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
