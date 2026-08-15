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
from pathlib import Path
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

    def _generate_mermaid_graph(self, events: list[DevTraceEvent]) -> str:
        """Generate a Mermaid flowchart representing the interaction graph."""
        lines = ["```mermaid", "graph TD", "  User([User / TUI Input])"]
        seen_edges: set[str] = set()
        node_ids: dict[str, str] = {"User": "User"}

        def _clean_id(name: str) -> str:
            return "".join(c if c.isalnum() else "_" for c in name).strip("_")

        last_node = "User"
        for i, e in enumerate(events):
            src_id = _clean_id(e.source)
            if src_id not in node_ids:
                node_ids[src_id] = src_id
                lines.append(f'  {src_id}["{e.source}"]')

            if e.event_type == TraceEventType.AGENT_ROUTING:
                target_agent = e.data.get("target_agent", "subagent")
                target_id = _clean_id(f"agent_{target_agent}")
                lines.append(f'  {target_id}[["🤖 Agent: {target_agent}"]]')
                edge = f"  {src_id} -->|Delegate| {target_id}"
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    lines.append(edge)
                last_node = target_id

            elif e.event_type == TraceEventType.TOOL_DISPATCH:
                tool_name = e.data.get("tool_name", e.action.replace("run(", "").replace(")", ""))
                tool_id = _clean_id(f"tool_{tool_name}_{i}")
                status_icon = "✓" if e.status == "OK" else "✗"
                lines.append(f'  {tool_id}["⚙️ Tool: {tool_name} ({status_icon})"]')
                edge = f"  {last_node} -->|Executes| {tool_id}"
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    lines.append(edge)

            elif e.event_type == TraceEventType.LLM_PAYLOAD:
                model_name = e.data.get("model", "LLM")
                llm_id = _clean_id(f"llm_{model_name}_{i}")
                tok_out = e.data.get("tokens_out", 0)
                lines.append(f'  {llm_id}{{"🧠 {model_name} (+{tok_out} tokens)"}}')
                edge = f"  {last_node} -->|Prompt| {llm_id}"
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    lines.append(edge)

        lines.append("```")
        return "\n".join(lines)

    def _generate_ascii_tree(self, events: list[DevTraceEvent]) -> str:
        """Generate a clean ASCII interaction trace tree."""
        lines = ["```text", "SAGO Execution Interaction Map:", "└── User Request"]
        current_indent = "    "

        for e in events:
            if e.event_type == TraceEventType.AGENT_ROUTING:
                target = e.data.get("target_agent", "agent")
                lines.append(f"{current_indent}├── 🤖 [SPAWN AGENT] {target}")
                current_indent += "│   "
            elif e.event_type == TraceEventType.TOOL_DISPATCH:
                tool = e.data.get("tool_name", e.action)
                dur = f"({e.duration_ms:.1f}ms)" if e.duration_ms > 0 else ""
                stat = "✓" if e.status == "OK" else "✗"
                lines.append(f"{current_indent}├── ⚙️ [TOOL] {tool} {stat} {dur}")
            elif e.event_type == TraceEventType.LLM_PAYLOAD:
                m = e.data.get("model", "LLM")
                t_in = e.data.get("tokens_in", 0)
                t_out = e.data.get("tokens_out", 0)
                lines.append(f"{current_indent}├── 🧠 [LLM] {m} (in: {t_in}, out: {t_out})")

        lines.append("```")
        return "\n".join(lines)

    def export_traces(
        self, file_path: str | Path | None = None, format: str = "json"
    ) -> tuple[bool, str]:
        """Export all recorded trace events to JSON or Markdown with complete interaction maps."""
        import json
        from pathlib import Path

        with self._lock:
            events = list(self._events)

        if not events:
            return False, "No trace events recorded to export."

        ts_str = time.strftime("%Y%m%d_%H%M%S")
        fmt = format.lower().strip().lstrip(".")
        if file_path is None or not str(file_path).strip():
            ext = "md" if fmt in ("md", "markdown") else "json"
            target_path = Path.cwd() / f"sago_trace_{ts_str}.{ext}"
        else:
            target_path = Path(file_path)
            if target_path.suffix in (".md", ".markdown"):
                fmt = "md"
            elif target_path.suffix in (".json",):
                fmt = "json"

        target_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            if fmt in ("md", "markdown"):
                mermaid_graph = self._generate_mermaid_graph(events)
                ascii_tree = self._generate_ascii_tree(events)

                lines = [
                    f"# SAGO Execution Trace Report ({ts_str})",
                    f"- **Total Events**: {len(events)}",
                    f"- **Export Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "",
                    "## 🗺️ Interaction Graph (Mermaid Flowchart)",
                    mermaid_graph,
                    "",
                    "## 🌲 Call Hierarchy Map",
                    ascii_tree,
                    "",
                    "## 📊 Event Summary",
                    "| Timestamp | Type | Source | Action | Status | Latency |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |",
                ]
                for e in events:
                    t_str = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                    dur = f"{e.duration_ms:.1f}ms" if e.duration_ms > 0 else "-"
                    lines.append(
                        f"| {t_str} | `{e.event_type.value}` | `{e.source}` | `{e.action}` | {e.status} | {dur} |"
                    )

                lines.append("\n## 🔍 Detailed Event Payloads\n")
                for idx, e in enumerate(events, 1):
                    lines.append(
                        f"### Event {idx}: {e.event_type.value} - {e.source} -> {e.action}"
                    )
                    lines.append(f"- **Status**: {e.status}")
                    lines.append(f"- **Latency**: {e.duration_ms:.2f}ms")
                    if e.data:
                        lines.append("```json")
                        lines.append(json.dumps(e.data, indent=2, default=str))
                        lines.append("```")
                    lines.append("")

                target_path.write_text("\n".join(lines), encoding="utf-8")
            else:
                # Build graph nodes & edges
                graph_nodes = []
                graph_edges = []
                for idx, e in enumerate(events):
                    graph_nodes.append(
                        {
                            "id": f"event_{idx}",
                            "type": e.event_type.value,
                            "source": e.source,
                            "action": e.action,
                            "status": e.status,
                            "duration_ms": e.duration_ms,
                        }
                    )
                    if idx > 0:
                        graph_edges.append(
                            {
                                "from": f"event_{idx - 1}",
                                "to": f"event_{idx}",
                                "type": "sequence",
                            }
                        )

                data = {
                    "export_timestamp": time.time(),
                    "export_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_events": len(events),
                    "interaction_graph": {
                        "nodes": graph_nodes,
                        "edges": graph_edges,
                    },
                    "events": [e.to_dict() for e in events],
                }
                target_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

            return True, str(target_path.resolve())
        except Exception as err:
            return False, f"Export failed: {err}"


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
