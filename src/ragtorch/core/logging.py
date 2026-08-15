"""Structured, context-aware logging built on Python's standard logging.

Library code always logs through the "ragtorch" logger via the
standard `logging` module — this lets a host application configure
handlers/levels/formatters itself, per Python's own guidance for
libraries. This module adds a thin structured layer on top: log calls
that carry an ExecutionContext automatically get run_id/parent_run_id
attached as `extra` fields, so log lines can be correlated with traces
and runs without callers threading those fields through by hand.

Safety rule (see ADR-003 / SECURITY.md): only metadata is logged by
default. Never log raw prompts, documents, retrieved content, or
secrets. Callers that need to log a payload must pass it through
`redact()` first, which defaults to omitting it entirely.
"""

from __future__ import annotations

import logging
from typing import Any

from ragtorch.core.context import ExecutionContext

logger = logging.getLogger("ragtorch")

_SENSITIVE_KEY_MARKERS = ("key", "token", "secret", "password", "authorization")


def get_logger(name: str = "ragtorch") -> logging.Logger:
    """Return a logger in the "ragtorch" hierarchy.

    Using a name under "ragtorch" (e.g. "ragtorch.retriever") lets the
    host application configure ragtorch's logs independently of its
    own, while still inheriting ragtorch's root configuration.
    """
    if name != "ragtorch" and not name.startswith("ragtorch."):
        name = f"ragtorch.{name}"
    return logging.getLogger(name)


def log_event(
    log: logging.Logger,
    level: int,
    message: str,
    context: ExecutionContext | None = None,
    **fields: Any,
) -> None:
    """Log ``message`` with structured fields, correlated to a run if given.

    ``fields`` becomes the log record's ``extra`` dict, prefixed so it
    cannot collide with LogRecord's own attributes (e.g. "message").
    """
    extra: dict[str, Any] = {f"ragtorch_{k}": v for k, v in fields.items()}
    if context is not None:
        extra["ragtorch_run_id"] = context.run_id
        extra["ragtorch_parent_run_id"] = context.parent_run_id
    log.log(level, message, extra=extra)


def redact(value: Any, *, allow: bool = False) -> Any:
    """Return a safe-to-log representation of a potentially sensitive value.

    By default, the value itself is never returned — only its type and
    length (when available) are, so a caller who forgets to think about
    sensitivity cannot accidentally leak a document, prompt, or secret
    into logs. Pass ``allow=True`` to explicitly opt in to logging the
    real value (only appropriate for content already known to be safe).
    """
    if allow:
        return value
    type_name = type(value).__name__
    try:
        length = len(value)
    except TypeError:
        return f"<redacted {type_name}>"
    return f"<redacted {type_name} len={length}>"


def is_sensitive_key(key: str) -> bool:
    """Heuristic: does this field name look like it holds a secret?"""
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)
