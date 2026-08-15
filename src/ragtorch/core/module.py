"""The Module contract: the core composable execution primitive.

Module remains the backward-compatible implementation primitive while the
v0.1 architecture evolves toward an explicit Component contract.
"""

from __future__ import annotations

import inspect
from collections import OrderedDict
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ragtorch.core.errors import ExecutionError, RegistryError
from ragtorch.core.events import Event, EventBus, EventType

if TYPE_CHECKING:
    from ragtorch.core.context import ExecutionContext

_bus = EventBus()

_forward_accepts_context_cache: dict[type, bool] = {}


def event_bus() -> EventBus:
    """Return the compatibility event bus used by Module execution."""
    return _bus


def _forward_accepts_context(cls: type[Module]) -> bool:
    """Does ``cls.forward`` declare a ``context`` parameter.

    Cached per class so reflection cost is paid once per Module subclass.
    """
    cached = _forward_accepts_context_cache.get(cls)
    if cached is not None:
        return cached
    signature = inspect.signature(cls.forward)
    accepts = "context" in signature.parameters
    _forward_accepts_context_cache[cls] = accepts
    return accepts


class Module:
    """Base class for every component in ragtorch.

    Subclasses implement :meth:`forward`. Calling the instance goes through
    :meth:`__call__`, which provides framework-level lifecycle behavior.
    Child modules assigned as attributes are automatically registered.
    """

    _modules: OrderedDict[str, Module]
    _name: str

    def __init__(self) -> None:
        object.__setattr__(self, "_modules", OrderedDict())
        object.__setattr__(self, "_name", self.__class__.__name__)

    def __setattr__(self, name: str, value: Any) -> None:
        modules = self.__dict__.get("_modules")
        if isinstance(value, Module) and modules is not None:
            self.register_module(name, value)
        object.__setattr__(self, name, value)

    def register_module(self, name: str, module: Module) -> None:
        """Explicitly register a child module under ``name``."""
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
        yield from self._modules.values()

    def named_children(self) -> Iterator[tuple[str, Module]]:
        yield from self._modules.items()

    def modules(self) -> Iterator[Module]:
        yield self
        for child in self._modules.values():
            yield from child.modules()

    def named_modules(self, prefix: str = "") -> Iterator[tuple[str, Module]]:
        yield prefix or self._name, self
        for name, child in self._modules.items():
            child_prefix = f"{prefix}.{name}" if prefix else name
            yield from child.named_modules(child_prefix)

    def __call__(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        if context is None:
            _bus.publish(Event(EventType.MODULE_STARTED, self._name))
            try:
                result = self.forward(input)
            except Exception as exc:
                _bus.publish(
                    Event(
                        EventType.MODULE_FAILED,
                        self._name,
                        payload={"error": str(exc)},
                    )
                )
                if isinstance(exc, RegistryError):
                    raise
                raise ExecutionError(
                    f"Module '{self._name}' raised {type(exc).__name__}: {exc}"
                ) from exc
            _bus.publish(Event(EventType.MODULE_FINISHED, self._name))
            return result

        run_id = context.run_id
        parent_run_id = context.parent_run_id
        _bus.publish(
            Event(
                EventType.MODULE_STARTED,
                self._name,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
        )
        try:
            if _forward_accepts_context(type(self)):
                result = self.forward(input, context=context)
            else:
                result = self.forward(input)
        except Exception as exc:
            _bus.publish(
                Event(
                    EventType.MODULE_FAILED,
                    self._name,
                    payload={"error": str(exc)},
                    run_id=run_id,
                    parent_run_id=parent_run_id,
                )
            )
            if isinstance(exc, RegistryError):
                raise
            raise ExecutionError(
                f"Module '{self._name}' raised {type(exc).__name__}: {exc}"
            ) from exc
        _bus.publish(
            Event(
                EventType.MODULE_FINISHED,
                self._name,
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
        )
        return result

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement forward().")

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
        child_reprs = "\n".join(
            f"  ({name}): {child!r}" for name, child in self._modules.items()
        )
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

    Its marker semantics are retained for backward compatibility while the
    v0.1 architecture defines a richer future Architecture contract.
    """
