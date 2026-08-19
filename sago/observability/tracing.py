"""Lightweight, stdlib-only observability/tracing for SAGO.

This module provides a minimal tracing layer built exclusively on the Python
standard library (``contextvars`` + ``logging``). It is fully OPT-IN:

- Nothing is active until :func:`start_trace` creates a collector via a
  :class:`contextvars.ContextVar`.
- If no trace is active, every helper (``start_span``, ``record_token_usage``,
  ``record_tool_call``, ``record_marker`` ...) is a safe no-op that returns
  immediately. There are no global side effects and no required configuration.

This makes it safe to instrument hot paths (tool execution, the LLM loop)
because with no active trace the cost is a single ``ContextVar.get()`` call.
"""

from __future__ import annotations

import contextvars
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("sago.observability.tracing")


@dataclass
class TokenUsage:
    """Aggregated token usage for a run."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        self.prompt_tokens += int(prompt_tokens or 0)
        self.completion_tokens += int(completion_tokens or 0)
        if total_tokens is None:
            total_tokens = (prompt_tokens or 0) + (completion_tokens or 0)
        self.total_tokens += int(total_tokens or 0)


@dataclass
class Span:
    """A single traced span with optional nested children."""

    name: str
    span_id: str
    parent_id: str | None
    start_time: float
    end_time: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[Span] = field(default_factory=list)

    @property
    def duration(self) -> float | None:
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


class TraceCollector:
    """Collects spans, token usage, tool timings, and markers for one run.

    A collector is bound to the current :mod:`contextvars` context so that
    concurrent runs (threads / asyncio tasks) keep independent traces.
    """

    def __init__(self) -> None:
        self.trace_id: str = uuid.uuid4().hex
        self.root_spans: list[Span] = []
        self._stack: list[Span] = []
        self.token_usage = TokenUsage()
        self.tool_calls: list[dict[str, Any]] = []
        self.markers: list[dict[str, Any]] = []
        self._start_time: float = time.time()

    # -- Span management -------------------------------------------------
    def start_span(self, name: str, **attributes: Any) -> Span:
        parent = self._stack[-1] if self._stack else None
        span = Span(
            name=name,
            span_id=uuid.uuid4().hex,
            parent_id=parent.span_id if parent else None,
            start_time=time.time(),
            attributes=dict(attributes),
        )
        if parent is not None:
            parent.children.append(span)
        else:
            self.root_spans.append(span)
        self._stack.append(span)
        return span

    def end_span(self, span: Span | None = None) -> None:
        now = time.time()
        if span is not None:
            if span.end_time is None:
                span.end_time = now
            if span in self._stack:
                self._stack.remove(span)
            return
        if self._stack:
            s = self._stack.pop()
            if s.end_time is None:
                s.end_time = now

    def _all_spans(self) -> list[Span]:
        out: list[Span] = []

        def _walk(spans: list[Span]) -> None:
            for s in spans:
                out.append(s)
                _walk(s.children)

        _walk(self.root_spans)
        return out

    # -- Record helpers --------------------------------------------------
    def record_token_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int | None = None,
        model: str | None = None,
        **extra: Any,
    ) -> None:
        self.token_usage.add(prompt_tokens, completion_tokens, total_tokens)
        if model is not None:
            extra["model"] = model
        if extra:
            self.markers.append({"kind": "token_usage", "data": dict(extra), "time": time.time()})

    def record_tool_call(
        self,
        name: str,
        duration: float | None = None,
        success: bool = True,
        error: str | None = None,
        **extra: Any,
    ) -> None:
        entry: dict[str, Any] = {
            "tool": name,
            "duration": duration,
            "success": success,
            "time": time.time(),
        }
        if error is not None:
            entry["error"] = error
        entry.update(extra)
        self.tool_calls.append(entry)

    def record_marker(self, kind: str, name: str | None = None, **extra: Any) -> None:
        self.markers.append({"kind": kind, "name": name, "data": dict(extra), "time": time.time()})

    # -- Aggregation -----------------------------------------------------
    def get_trace(self) -> dict[str, Any]:
        spans = self._all_spans()
        total_tool_duration = sum(
            (c["duration"] or 0) for c in self.tool_calls if c["duration"] is not None
        )
        return {
            "trace_id": self.trace_id,
            "duration": time.time() - self._start_time,
            "span_count": len(spans),
            "spans": [s.to_dict() for s in self.root_spans],
            "token_usage": {
                "prompt_tokens": self.token_usage.prompt_tokens,
                "completion_tokens": self.token_usage.completion_tokens,
                "total_tokens": self.token_usage.total_tokens,
            },
            "tool_calls": list(self.tool_calls),
            "tool_call_count": len(self.tool_calls),
            "tool_duration": total_tool_duration,
            "markers": list(self.markers),
        }


# ---------------------------------------------------------------------------
# Module-level, context-bound API (opt-in, no-op when no trace is active)
# ---------------------------------------------------------------------------

_current_collector: contextvars.ContextVar[TraceCollector | None] = contextvars.ContextVar(
    "sago_trace_collector", default=None
)

# A reusable no-op span returned when no trace is active, so callers can always
# pass the result of start_span(...) to end_span(...) without special casing.
_NULL_SPAN = Span(
    name="<inactive>",
    span_id="",
    parent_id=None,
    start_time=0.0,
    end_time=0.0,
)


def start_trace() -> TraceCollector:
    """Create and activate a new trace collector for the current context."""
    collector = TraceCollector()
    _current_collector.set(collector)
    return collector


def get_collector() -> TraceCollector | None:
    """Return the active collector, or ``None`` if tracing is not enabled."""
    return _current_collector.get()


def stop_trace() -> None:
    """Deactivate tracing for the current context."""
    _current_collector.set(None)


def start_span(name: str, **attributes: Any) -> Span:
    """Start a (possibly nested) span. Returns a no-op span if no trace active."""
    collector = _current_collector.get()
    if collector is None:
        return _NULL_SPAN
    return collector.start_span(name, **attributes)


def end_span(span: Span | None = None) -> None:
    """End a span. Safe no-op when no trace is active."""
    collector = _current_collector.get()
    if collector is None:
        return
    collector.end_span(span)


class span:
    """Context manager that opens and closes a span around a block.

    Usage::

        with span("llm:chat", model="gpt-4o"):
            response = client.chat.completions.create(...)

    When no trace is active this is a no-op context manager.
    """

    __slots__ = ("_name", "_attributes", "_span")

    def __init__(self, name: str, **attributes: Any) -> None:
        self._name = name
        self._attributes = attributes
        self._span: Span | None = None

    def __enter__(self) -> Span:
        self._span = start_span(self._name, **self._attributes)
        return self._span

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        end_span(self._span)
        self._span = None


def record_token_usage(
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    model: str | None = None,
    **extra: Any,
) -> None:
    """Record LLM token usage for the current run (no-op when inactive)."""
    collector = _current_collector.get()
    if collector is None:
        return
    collector.record_token_usage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model=model,
        **extra,
    )


def record_tool_call(
    name: str,
    duration: float | None = None,
    success: bool = True,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Record a per-tool call timing / outcome (no-op when inactive)."""
    collector = _current_collector.get()
    if collector is None:
        return
    collector.record_tool_call(name=name, duration=duration, success=success, error=error, **extra)


def record_marker(kind: str, name: str | None = None, **extra: Any) -> None:
    """Record an arbitrary agent / step marker (no-op when inactive)."""
    collector = _current_collector.get()
    if collector is None:
        return
    collector.record_marker(kind, name, **extra)


def get_trace() -> dict[str, Any] | None:
    """Return the aggregated trace for the current run, or ``None`` if inactive."""
    collector = _current_collector.get()
    if collector is None:
        return None
    return collector.get_trace()


def trace_tool(name: str, fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run ``fn(*args, **kwargs)`` inside a tool span.

    Tracing never affects the wrapped call: any tracing error is swallowed and
    the original return value (or exception) is propagated unchanged.
    """
    _span = start_span(f"tool:{name}", tool=name)
    ok = True
    try:
        return fn(*args, **kwargs)
    except Exception:
        ok = False
        raise
    finally:
        try:
            duration = _span.duration
            if ok:
                record_tool_call(name, duration=duration, success=True)
            else:
                record_tool_call(name, duration=duration, success=False)
        except Exception:
            logger.debug("trace_tool instrumentation failed for %s", name, exc_info=True)
        finally:
            try:
                end_span(_span)
            except Exception as e:
                logger.debug("end_span failed for %s", name, exc_info=e)
