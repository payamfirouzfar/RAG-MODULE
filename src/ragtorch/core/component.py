"""Public structural contract for executable RAG components.

Component is deliberately minimal: name, component_type, and a callable
execution interface. It exists so future RAG components (Retriever,
Generator, Embedder, Reranker, ...) can be recognized by the framework
without inheriting from Module or any ragtorch base class — see ADR-010.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from ragtorch.core.context import ExecutionContext

InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class Component(Protocol[InputT, OutputT]):
    """Structural contract implemented by executable RAG components.

    A Component has a human-readable name, a component type descriptor,
    and a callable execution interface with optional explicit execution
    context. The protocol is intentionally provider-agnostic and does
    not require inheritance from Module — see ADR-010.
    """

    @property
    def name(self) -> str:
        """Return the component's runtime name."""
        ...

    @property
    def component_type(self) -> str:
        """Return the component's type descriptor."""
        ...

    def __call__(
        self,
        input: InputT,
        *,
        context: ExecutionContext | None = None,
    ) -> OutputT:
        """Execute the component."""
        ...
