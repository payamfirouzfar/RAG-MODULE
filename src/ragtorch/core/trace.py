"""Trace: a vendor-neutral internal representation of how execution
moved through a tree of modules.

This intentionally does not depend on OpenTelemetry or any other
observability vendor. A Trace can be exported to one later; the core
must not require it. See ADR-003.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def new_span_id() -> str:
    return f"span_{uuid.uuid4().hex}"


@dataclass
class Span:
    """One timed unit of work within a Trace, optionally nested under
    a parent span."""

    name: str
    span_id: str = field(default_factory=new_span_id)
    parent_span_id: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    finished_at: float | None = None
    status: str = "ok"
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        if self.finished_at is None:
            return None
        return self.finished_at - self.started_at

    def finish(self, status: str = "ok") -> Span:
        self.finished_at = time.monotonic()
        self.status = status
        return self


class Trace:
    """A tree of spans recorded during one execution.

    Spans are created via :meth:`start_span`, used as a context
    manager, and automatically finished (with ``status="error"`` if
    the block raised) on exit.
    """

    def __init__(self) -> None:
        self._spans: list[Span] = []
        self._stack: list[Span] = []

    def start_span(self, name: str, **attributes: Any) -> _SpanContext:
        parent = self._stack[-1] if self._stack else None
        span = Span(
            name=name,
            parent_span_id=parent.span_id if parent else None,
            attributes=attributes,
        )
        self._spans.append(span)
        return _SpanContext(self, span)

    @property
    def spans(self) -> list[Span]:
        return list(self._spans)

    def root_spans(self) -> list[Span]:
        return [s for s in self._spans if s.parent_span_id is None]

    def children_of(self, span_id: str) -> list[Span]:
        return [s for s in self._spans if s.parent_span_id == span_id]

    def render(self) -> str:
        """Return a human-readable indented tree of the trace."""
        lines: list[str] = []
        for root in self.root_spans():
            self._render_span(root, indent="", lines=lines)
        return "\n".join(lines)

    def _render_span(self, span: Span, indent: str, lines: list[str]) -> None:
        duration_ms = f"{span.duration * 1000:.2f} ms" if span.duration is not None else "..."
        lines.append(f"{indent}{span.name}  {duration_ms}")
        for child in self.children_of(span.span_id):
            self._render_span(child, indent + "    ", lines)


class _SpanContext:
    """Context manager returned by Trace.start_span."""

    def __init__(self, trace: Trace, span: Span) -> None:
        self._trace = trace
        self._span = span

    def __enter__(self) -> Span:
        self._trace._stack.append(self._span)
        return self._span

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._span.finish(status="error" if exc_type is not None else "ok")
        self._trace._stack.pop()
