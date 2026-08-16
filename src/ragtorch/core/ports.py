"""Component boundary metadata: InputPort, OutputPort, is_compatible,
check_connection.

Ports describe a component's input/output boundary as inspectable
architecture metadata, separate from (and not attached to) Component
itself. See ADR-011 for the full design rationale, including why port
types must be real Python classes (not strings, not generic aliases),
why ports are never derived from __call__ annotations via reflection,
and why compatibility is deliberately conservative (exact/subtype only).

check_connection() (ADR-014) is a thin, raising precondition wrapper
over is_compatible(): a future Block/composition layer can use it to
fail fast on an illegal connection, without is_compatible() itself
losing its bool-returning, side-effect-free predicate contract.
"""

from __future__ import annotations

import types
from dataclasses import dataclass

from ragtorch.core.errors import ValidationError


def _is_concrete_class(value: object) -> bool:
    """Is ``value`` an actual Python class, not a generic alias?

    isinstance(x, type) is NOT a reliable way to detect this across the
    project's supported Python range: on Python 3.10, a builtin generic
    alias such as ``list[Document]`` (an instance of
    ``types.GenericAlias``) reports ``isinstance(list[Document], type)
    is True`` — this changed to ``False`` in a later 3.x release.
    Verified directly against 3.10/3.12 interpreters, not assumed;
    caught by CI (which runs 3.10/3.11/3.12) after passing on a local
    3.12-only environment. ``types.GenericAlias`` is therefore excluded
    explicitly, on every supported version, regardless of what
    isinstance(x, type) happens to report there.
    """
    return isinstance(value, type) and not isinstance(value, types.GenericAlias)


@dataclass(frozen=True)
class InputPort:
    """Describe the input boundary of a component."""

    name: str
    type: type

    def __post_init__(self) -> None:
        if not _is_concrete_class(self.type):
            raise ValidationError(
                f"InputPort '{self.name}' requires a Python class as type, got {self.type!r}."
            )


@dataclass(frozen=True)
class OutputPort:
    """Describe the output boundary of a component."""

    name: str
    type: type

    def __post_init__(self) -> None:
        if not _is_concrete_class(self.type):
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


def check_connection(output: OutputPort, input: InputPort) -> None:
    """Raise ValidationError if ``output`` cannot feed ``input``.

    A precondition/enforcement counterpart to is_compatible() (ADR-014):
    "ask" (is_compatible, bool) vs. "enforce" (check_connection, raises).
    check_connection() never re-implements compatibility logic itself —
    its body is exactly a call to is_compatible() — so is_compatible()
    remains the single source of truth for what "compatible" means; any
    future change to that logic is automatically inherited here.

    check_connection() only checks whether a proposed connection would
    be legal. It does not register, store, mutate, wire, or execute an
    actual connection between components, and it does not modify either
    Port.

    Assumes ``output``/``input`` are real OutputPort/InputPort
    instances, exactly as is_compatible() does. Passing anything else
    is programmer misuse and is not normalized into ValidationError in
    this version — see ADR-014.
    """
    if not is_compatible(output, input):
        raise ValidationError(
            f"Cannot connect output {output.name!r} ({output.type.__name__}) "
            f"to input {input.name!r} ({input.type.__name__}): incompatible types."
        )
