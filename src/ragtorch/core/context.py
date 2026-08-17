"""Execution identity: a small, immutable transport object.

ExecutionContext exists so that logs, traces, metrics, and evaluation
artifacts can all be attributed to "the same execution" without relying
on process-wide global state. It carries an identity (run_id, and an
optional parent_run_id for nested executions) plus arbitrary metadata.

This is deliberately small. It is not a place to put configuration,
loggers, or business data — see ADR-002 for the reasoning.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ragtorch.core.events import EventScope


def new_run_id() -> str:
    """Generate a new unique run identifier."""
    return f"run_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class ExecutionContext:
    """Identity and metadata for one execution.

    ``metadata`` is copied into an immutable mapping at construction time
    so a context handed to multiple components cannot be mutated by one
    of them to affect what the others see.
    """

    run_id: str = field(default_factory=new_run_id)
    parent_run_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    event_scope: EventScope | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def child(self, **metadata: Any) -> ExecutionContext:
        """Create a new context representing a nested execution.

        The child gets a fresh run_id, records this context's run_id as
        its parent_run_id, and merges any additional metadata on top of
        the parent's. event_scope is propagated unchanged -- the same
        object (see ADR-022), not a new one.
        """
        merged = {**self.metadata, **metadata}
        return ExecutionContext(
            run_id=new_run_id(),
            parent_run_id=self.run_id,
            metadata=merged,
            event_scope=self.event_scope,
        )
