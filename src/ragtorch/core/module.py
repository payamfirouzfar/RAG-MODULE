"""The Module contract: the core composable execution primitive.

Module remains the concrete implementation primitive. It structurally
satisfies the public Component contract (ragtorch.core.component) via
the name/component_type properties below, without inheriting from it —
see ADR-010.
"""

from __future__ import annotations

import inspect
from collections import OrderedDict
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ragtorch.core.errors import ExecutionError, RegistryError
from ragtorch.core.events import Event, EventBus, EventType

if TYPE_CHECKING:
    from ragtorch.core.block import Block
    from ragtorch.core.composition import CompositionGraph
    from ragtorch.core.context import ExecutionContext
    from ragtorch.core.inspection import ArchitectureNode, ArchitectureSnapshot

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

    @property
    def name(self) -> str:
        """Return the module's runtime name (see ADR-010: Component contract)."""
        return self._name

    @property
    def component_type(self) -> str:
        """Return the module's component type descriptor (see ADR-010).

        Currently ``type(self).__name__`` — descriptive identity, not
        yet a stable serialization identifier.
        """
        return type(self).__name__

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
        scope = context.event_scope

        started = Event(
            EventType.MODULE_STARTED,
            self._name,
            run_id=run_id,
            parent_run_id=parent_run_id,
        )
        _bus.publish(started)
        if scope is not None:
            scope.publish(started)
        try:
            if _forward_accepts_context(type(self)):
                result = self.forward(input, context=context)
            else:
                result = self.forward(input)
        except Exception as exc:
            failed = Event(
                EventType.MODULE_FAILED,
                self._name,
                payload={"error": str(exc)},
                run_id=run_id,
                parent_run_id=parent_run_id,
            )
            _bus.publish(failed)
            if scope is not None:
                scope.publish(failed)
            if isinstance(exc, RegistryError):
                raise
            raise ExecutionError(
                f"Module '{self._name}' raised {type(exc).__name__}: {exc}"
            ) from exc
        finished = Event(
            EventType.MODULE_FINISHED,
            self._name,
            run_id=run_id,
            parent_run_id=parent_run_id,
        )
        _bus.publish(finished)
        if scope is not None:
            scope.publish(finished)
        return result

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        raise NotImplementedError(f"{type(self).__name__} must implement forward().")

    def snapshot(self) -> ArchitectureSnapshot:
        """Return the canonical, immutable architecture snapshot (ADR-012).

        This is the single source of truth for this module's structure;
        inspect() renders text from it rather than walking the tree a
        second, independent way.
        """
        from ragtorch.core.inspection import snapshot as _snapshot

        return _snapshot(self)

    def inspect(self) -> str:
        """Return a detailed, indented tree of this module's architecture."""
        arch = self.snapshot()
        children_by_parent: dict[str, list[str]] = {}
        for child in arch.children:
            children_by_parent.setdefault(child.parent_id, []).append(child.child_id)
        nodes_by_id = {node.id: node for node in arch.nodes}

        lines: list[str] = []
        module_count = len(arch.nodes)
        depth = _snapshot_depth(arch.nodes[0].id, children_by_parent)
        lines.append("Architecture")
        lines.append("-" * 12)
        lines.append("")
        lines.append(f"Modules: {module_count}")
        lines.append(f"Depth: {depth}")
        lines.append("")
        lines.append(self._name)
        lines.extend(
            _render_children(arch.nodes[0].id, children_by_parent, nodes_by_id, indent="    ")
        )
        return "\n".join(lines)

    def __repr__(self) -> str:
        if not self._modules:
            return f"{self._name}()"
        child_reprs = "\n".join(f"  ({name}): {child!r}" for name, child in self._modules.items())
        return f"{self._name}(\n{child_reprs}\n)"


def _render_children(
    node_id: str,
    children_by_parent: dict[str, list[str]],
    nodes_by_id: dict[str, ArchitectureNode],
    indent: str,
) -> list[str]:
    lines: list[str] = []
    for child_id in children_by_parent.get(node_id, []):
        child = nodes_by_id[child_id]
        display_name = child_id.rsplit(".", 1)[-1]
        lines.append(f"{indent}{display_name} ({child.component_type})")
        lines.extend(_render_children(child_id, children_by_parent, nodes_by_id, indent + "    "))
    return lines


def _snapshot_depth(node_id: str, children_by_parent: dict[str, list[str]]) -> int:
    child_ids = children_by_parent.get(node_id, [])
    if not child_ids:
        return 1
    return 1 + max(_snapshot_depth(child_id, children_by_parent) for child_id in child_ids)


class RAGModule(Module):
    """Marker base class for top-level, RAG-specific systems.

    Its marker semantics are retained for backward compatibility;
    subclassing RAGModule and overriding forward() remains fully
    supported and unchanged. from_graph() (ADR-021) is an additive
    construction path for graph-backed architectures, delegating
    execution entirely to Block -- no second execution system.
    """

    @classmethod
    def from_graph(
        cls,
        graph: CompositionGraph,
        *,
        input_node: str,
        output_node: str,
    ) -> RAGModule:
        """Build a graph-backed RAGModule delegating execution to Block.

        Returns an actual RAGModule instance (isinstance(result,
        RAGModule) is True) wrapping a Block internally. input_node/
        output_node are required exactly as Block requires them -- no
        entry/exit-node inference, no re-validation of Block's own
        construction-time checks. Not promised to work on an arbitrary
        RAGModule subclass in this version -- see ADR-021 Q3.
        """
        # Deferred import: block.py imports Module from this module at
        # module scope, so a top-level import here would be circular.
        # Mirrors Module.snapshot()'s existing lazy-import pattern.
        from ragtorch.core.block import Block

        block = Block(graph, input_node=input_node, output_node=output_node)
        return _GraphBackedRAGModule(block)


class _GraphBackedRAGModule(RAGModule):
    """Private adapter: a RAGModule that delegates forward() to a
    Block. Not part of the public API -- construct via
    RAGModule.from_graph(), never directly.
    """

    def __init__(self, block: Block) -> None:
        super().__init__()
        self._block = block  # single registration via __setattr__ -- see ADR-021 Q6

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        return self._block(input, context=context)
