"""Component boundary metadata: InputPort, OutputPort, is_compatible.

Ports describe a component's input/output boundary as inspectable
architecture metadata, separate from (and not attached to) Component
itself. See ADR-011 for the full design rationale, including why port
types must be real Python classes (not strings, not generic aliases),
why ports are never derived from __call__ annotations via reflection,
and why compatibility is deliberately conservative (exact/subtype only).
"""

from __future__ import annotations

from dataclasses import dataclass

from ragtorch.core.errors import ValidationError


@dataclass(frozen=True)
class InputPort:
    """Describe the input boundary of a component."""

    name: str
    type: type

    def __post_init__(self) -> None:
        if not isinstance(self.type, type):
            raise ValidationError(
                f"InputPort '{self.name}' requires a Python class as type, got {self.type!r}."
            )


@dataclass(frozen=True)
class OutputPort:
    """Describe the output boundary of a component."""

    name: str
    type: type

    def __post_init__(self) -> None:
        if not isinstance(self.type, type):
            raise ValidationError(
                f"OutputPort '{self.name}' requires a Python class as type, got {self.type!r}."
            )


def is_compatible(output: OutputPort, input: InputPort) -> bool:
    """Return whether an output port can feed an input port.

    issubclass(T, T) is True, so this single check implements both
    exact-match and subtype compatibility. Generic aliases, unions,
    structural typing, and other advanced typing constructs are
    intentionally unsupported in this version (see ADR-011).
    """
    return issubclass(output.type, input.type)
