"""The Module contract: the single most important abstraction in ragtorch.

Every component in the framework — chunkers, retrievers, routers, and
eventually full RAG systems — is a Module. A Module is callable, may
own named child modules, and can describe its own architecture.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from ragtorch.core.errors import ExecutionError, RegistryError
from ragtorch.core.events import Event, EventBus, EventType

_bus = EventBus()


def event_bus() -> EventBus:
    """Return the process-wide event bus used by Module execution."""
    return _bus


class Module:
    """Base class for every component in ragtorch.

    Subclasses implement :meth:`forward`. Calling the instance goes
    through :meth:`__call__`, which is responsible for framework-level
    behavior (currently: start/finish/fail events and error wrapping)
    while ``forward`` holds the component's actual logic.

    Child modules assigned as attributes are automatically registered,
    mirroring the ergonomics of ``self.chunker = Chunker()`` making the
    chunker discoverable via :meth:`named_modules`.
    """

    _modules: OrderedDict[str, Module]
    _name: str

    def __init__(self) -> None:
        # Must be set before any attribute assignment triggers __setattr__.
        object.__setattr__(self, "_modules", OrderedDict())
        object.__setattr__(self, "_name", self.__class__.__name__)

    # -- registration ------------------------------------------------

    def __setattr__(self, name: str, value: Any) -> None:
        modules = self.__dict__.get("_modules")
        if isinstance(value, Module) and modules is not None:
            self.register_module(name, value)
        object.__setattr__(self, name, value)

    def register_module(self, name: str, module: Module) -> None:
        """Explicitly register a child module under ``name``.

        Raises RegistryError if ``name`` is already registered to a
        different module instance.
        """
        if not isinstance(module, Module):
            raise RegistryError(
                f"Cannot register '{name}': expected a Module instance, "
                f"got {type(module).__name__}."
            )
        existing = self._modules.get(name)
        if existing is not None and existing is not module:
            raise RegistryError(
                f"Module '{name}' cannot be registered because a module "
                f"with the name '{name}' already exists.\n\n"
                f"Existing module:\n    {type(existing).__name__}\n\n"
                f"Attempted module:\n    {type(module).__name__}"
            )
        self._modules[name] = module

    def children(self) -> Iterator[Module]:
        """Yield immediate child modules."""
        yield from self._modules.values()

    def named_children(self) -> Iterator[tuple[str, Module]]:
        """Yield (name, module) pairs for immediate children."""
        yield from self._modules.items()

    def modules(self) -> Iterator[Module]:
        """Yield self and all descendant modules, depth-first."""
        yield self
        for child in self._modules.values():
            yield from child.modules()

    def named_modules(self, prefix: str = "") -> Iterator[tuple[str, Module]]:
        """Yield (dotted_name, module) pairs for self and all descendants."""
        yield prefix or self._name, self
        for name, child in self._modules.items():
            child_prefix = f"{prefix}.{name}" if prefix else name
            yield from child.named_modules(child_prefix)

    # -- execution -----------------------------------------------------

    def __call__(self, input: Any) -> Any:
        _bus.publish(Event(EventType.MODULE_STARTED, self._name))
        try:
            result = self.forward(input)
        except Exception as exc:
            _bus.publish(Event(EventType.MODULE_FAILED, self._name, payload={"error": str(exc)}))
            if isinstance(exc, RegistryError):
                raise
            raise ExecutionError(
                f"Module '{self._name}' raised {type(exc).__name__}: {exc}"
            ) from exc
        _bus.publish(Event(EventType.MODULE_FINISHED, self._name))
        return result

    def forward(self, input: Any) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement forward().")

    # -- inspection ------------------------------------------------------

    def inspect(self) -> str:
        """Return a detailed, indented tree of this module's architecture."""
        lines: list[str] = []
        module_count = sum(1 for _ in self.modules())
        depth = _max_depth(self)
        lines.append("Architecture")
        lines.append("-" * 12)
        lines.append("")
        lines.append(f"Modules: {module_count}")
        lines.append(f"Depth: {depth}")
        lines.append("")
        lines.append(self._name)
        lines.extend(_inspect_children(self, indent="    "))
        return "\n".join(lines)

    def __repr__(self) -> str:
        if not self._modules:
            return f"{self._name}()"
        child_reprs = "\n".join(f"  ({name}): {child!r}" for name, child in self._modules.items())
        return f"{self._name}(\n{child_reprs}\n)"


def _inspect_children(module: Module, indent: str) -> list[str]:
    lines: list[str] = []
    for name, child in module.named_children():
        lines.append(f"{indent}{name} ({type(child).__name__})")
        lines.extend(_inspect_children(child, indent + "    "))
    return lines


def _max_depth(module: Module) -> int:
    children = list(module.children())
    if not children:
        return 1
    return 1 + max(_max_depth(child) for child in children)


class RAGModule(Module):
    """Marker base class for top-level, RAG-specific systems.

    Semantically distinct from a generic :class:`Module` so framework
    code and users can identify top-level RAG systems via
    ``isinstance(x, RAGModule)``.
    """
