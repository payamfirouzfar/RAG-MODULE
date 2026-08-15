"""Sequential composition of modules.

``Sequential`` chains modules so that each module's output becomes the
next module's input. It is itself a Module, so a Sequential can be
nested inside another Sequential or any other composite.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ragtorch.core.module import Module


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

    def forward(self, input: Any) -> Any:
        value = input
        for step in self._steps:
            value = step(value)
        return value

    def __len__(self) -> int:
        return len(self._steps)

    def __iter__(self) -> Iterator[Module]:
        return iter(self._steps)

    def __getitem__(self, index: int) -> Module:
        return self._steps[index]
