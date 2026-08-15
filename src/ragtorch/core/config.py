"""Explicit, immutable-by-default configuration objects.

Configuration is data, not global mutable state. Instances are frozen
dataclasses so components can be handed an explicit config object and
trust it will not change underneath them.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from ragtorch.core.errors import ConfigurationError


@dataclass(frozen=True)
class RAGConfig:
    """Base configuration object.

    Subclass this for component-specific configuration. Instances are
    frozen; use :meth:`with_overrides` to derive a modified copy rather
    than mutating in place.
    """

    debug: bool = False
    tracing: bool = False
    profiling: bool = False

    def with_overrides(self, **changes: Any) -> RAGConfig:
        unknown = set(changes) - {f.name for f in dataclasses.fields(self)}
        if unknown:
            raise ConfigurationError(
                f"Unknown configuration field(s): {sorted(unknown)}. "
                f"Valid fields: {sorted(f.name for f in dataclasses.fields(self))}"
            )
        return dataclasses.replace(self, **changes)
