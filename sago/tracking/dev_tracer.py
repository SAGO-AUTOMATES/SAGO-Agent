"""Developer Mode Telemetry & Live Trace Engine for SAGO.

Provides microsecond execution tracing, function call interception,
LLM payload inspection, tool dispatch monitoring, and real-time debug streams.
"""

from __future__ import annotations

import collections
import contextlib
import logging
import threading
import time
from collections.abc import Callable, Generator
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("sago.tracking.dev_tracer")


class TraceEventType(StrEnum):
    FUNCTION_CALL = "FUNCTION_CALL"
    FUNCTION_RETURN = "FUNCTION_RETURN"
    LLM_PAYLOAD = "LLM_PAYLOAD"
    TOOL_DISPATCH = "TOOL_DISPATCH"
    AGENT_ROUTING = "AGENT_ROUTING"
    LOG_EVENT = "LOG_EVENT"
    STATE_CHANGE = "STATE_CHANGE"


@dataclass
class DevTraceEvent:
    """A single developer trace event."""

    timestamp: float
    event_type: TraceEventType
    source: str
    action: str
    data: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    status: str = "OK"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    def format_line(self) -> str:
        """Formatted human-readable line for developer logs."""
        t_str = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        ms = int((self.timestamp % 1) * 1000)
        time_tag = f"{t_str}.{ms:03d}"
        dur_tag = f" ({self.duration_ms:.1f}ms)" if self.duration_ms > 0 else ""
        status_tag = f" [{self.status}]" if self.status != "OK" else ""
        return f"[{time_tag}] [{self.event_type.value}] {self.source} -> {self.action}{dur_tag}{status_tag}"


class DevTracer:
    """Thread-safe telemetry and developer trace manager."""

    def __init__(self, max_events: int = 1000) -> None:
        self._events: collections.deque[DevTraceEvent] = collections.deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._enabled = False
        self._listeners: list[Callable[[DevTraceEvent], None]] = []

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled

    def add_listener(self, listener: Callable[[DevTraceEvent], None]) -> None:
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[DevTraceEvent], None]) -> None:
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    def record(
        self,
        event_type: TraceEventType,
        source: str,
        action: str,
        data: dict[str, Any] | None = None,
        duration_ms: float = 0.0,
        status: str = "OK",
    ) -> DevTraceEvent:
        """Record a trace event and notify active listeners."""
        event = DevTraceEvent(
            timestamp=time.time(),
            event_type=event_type,
            source=source,
            action=action,
            data=data or {},
            duration_ms=duration_ms,
            status=status,
        )

        with self._lock:
            self._events.append(event)
            listeners = list(self._listeners)

        if self._enabled:
            for cb in listeners:
                try:
                    cb(event)
                except Exception as e:
                    logger.debug("Trace listener error: %s", e)

        return event

    @contextlib.contextmanager
    def trace_block(
        self,
        source: str,
        action: str,
        event_type: TraceEventType = TraceEventType.FUNCTION_CALL,
        data: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        """Context manager to measure execution latency and trace enter/exit."""
        start_time = time.perf_counter()
        ctx_data = dict(data or {})
        self.record(event_type, source, f"START: {action}", data=ctx_data)
        status = "OK"
        try:
            yield ctx_data
        except Exception as e:
            status = f"ERROR: {type(e).__name__}"
            ctx_data["error"] = str(e)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return_type = (
                TraceEventType.FUNCTION_RETURN
                if event_type == TraceEventType.FUNCTION_CALL
                else event_type
            )
            self.record(
                return_type,
                source,
                f"FINISH: {action}",
                data=ctx_data,
                duration_ms=elapsed_ms,
                status=status,
            )

    def get_recent_traces(
        self, limit: int = 50, filter_type: TraceEventType | None = None
    ) -> list[DevTraceEvent]:
        """Retrieve recent trace events with optional type filtering."""
        with self._lock:
            events = list(self._events)
        if filter_type is not None:
            events = [e for e in events if e.event_type == filter_type]
        return events[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


_GLOBAL_TRACER: DevTracer | None = None
_TRACER_INIT_LOCK = threading.Lock()


def get_dev_tracer() -> DevTracer:
    """Get or initialize global DevTracer singleton."""
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is None:
        with _TRACER_INIT_LOCK:
            if _GLOBAL_TRACER is None:
                _GLOBAL_TRACER = DevTracer()
    return _GLOBAL_TRACER
