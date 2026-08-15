"""Sequential composition of modules.

``Sequential`` chains modules so that each module's output becomes the
next module's input. It is itself a Module, so a Sequential can be
nested inside another Sequential or any other composite.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from ragtorch.core.module import Module

if TYPE_CHECKING:
    from ragtorch.core.context import ExecutionContext


class Sequential(Module):
    """Run child modules one after another, threading output to input.

    An empty Sequential is the identity function.
    """

    def __init__(self, *steps: Module) -> None:
        super().__init__()
        self._steps: list[Module] = []
        for i, step in enumerate(steps):
            name = f"step{i}"
            self.register_module(name, step)
            self._steps.append(step)

    def forward(self, input: Any, *, context: ExecutionContext | None = None) -> Any:
        value = input
        for i, step in enumerate(self._steps):
            if context is not None:
                value = step(value, context=context.child(step=f"step{i}"))
            else:
                value = step(value)
        return value

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self) -> Iterator[Module]:
        return iter(self._steps)

    def __getitem__(self, index: int) -> Module:
        return self._steps[index]
