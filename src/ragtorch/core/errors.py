"""Framework-level exception hierarchy.

All exceptions raised by ragtorch's core inherit from RAGTorchError so
callers can catch the whole family with a single except clause.
"""

from __future__ import annotations


class RAGTorchError(Exception):
    """Base class for all ragtorch exceptions."""


class ConfigurationError(RAGTorchError):
    """Raised when configuration is invalid or inconsistent."""


class ModuleError(RAGTorchError):
    """Raised for generic module-related failures."""


class ExecutionError(RAGTorchError):
    """Raised when execution of a module or pipeline fails."""


class RegistryError(RAGTorchError):
    """Raised when module registration is invalid (e.g. duplicate name)."""


class ValidationError(RAGTorchError):
    """Raised when input/output validation fails."""
