"""Developer Mode Telemetry & Live Trace Engine for SAGO.

Provides microsecond execution tracing, function call interception,
LLM payload inspection, tool dispatch monitoring, and real-time debug streams.
"""

from __future__ import annotations

import collections
import contextlib
import json
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
    LLM_RAW_REQUEST = "LLM_RAW_REQUEST"
    LLM_RAW_RESPONSE = "LLM_RAW_RESPONSE"
    LLM_THINKING = "LLM_THINKING"
    TOOL_DISPATCH = "TOOL_DISPATCH"
    AGENT_ROUTING = "AGENT_ROUTING"
    PROMPT_ENHANCED = "PROMPT_ENHANCED"
    LOG_EVENT = "LOG_EVENT"
    STATE_CHANGE = "STATE_CHANGE"
    ERROR = "ERROR"
    RETRY = "RETRY"
    PERMISSION_CHECK = "PERMISSION_CHECK"


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

    def get_events(
        self, limit: int = 0, filter_type: TraceEventType | None = None
    ) -> list[DevTraceEvent]:
        """Alias for get_recent_traces. limit=0 means all events."""
        return self.get_recent_traces(limit=limit or 99999, filter_type=filter_type)

    def get_event_count(self) -> int:
        """Return total number of events in buffer."""
        with self._lock:
            return len(self._events)

    def record_llm_request(
        self,
        source: str,
        model: str,
        messages: list[dict[str, Any]],
        system_prompt: str = "",
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> DevTraceEvent:
        """Record the raw LLM request payload."""
        data = {
            "model": model,
            "messages": messages,
            "messages_count": len(messages),
            "system_prompt": system_prompt[:5000] if system_prompt else "",
            "system_prompt_truncated": len(system_prompt) > 5000 if system_prompt else False,
            "tools_count": len(tools) if tools else 0,
            "tools": tools[:10] if tools else [],
            **kwargs,
        }
        return self.record(
            TraceEventType.LLM_RAW_REQUEST, source, f"LLM REQUEST -> {model}", data=data
        )

    def record_llm_response(
        self,
        source: str,
        model: str,
        response_content: str,
        thinking: str = "",
        tool_calls: list[dict[str, Any]] | None = None,
        usage: dict[str, Any] | None = None,
        finish_reason: str = "",
        latency_ms: float = 0.0,
        **kwargs: Any,
    ) -> DevTraceEvent:
        """Record the raw LLM response content including thinking."""
        data = {
            "model": model,
            "response_content": response_content[:10000] if response_content else "",
            "response_truncated": len(response_content) > 10000 if response_content else False,
            "thinking": thinking[:10000] if thinking else "",
            "thinking_truncated": len(thinking) > 10000 if thinking else False,
            "thinking_length": len(thinking) if thinking else 0,
            "tool_calls": tool_calls or [],
            "tool_calls_count": len(tool_calls) if tool_calls else 0,
            "usage": usage or {},
            "finish_reason": finish_reason,
            **kwargs,
        }
        status = "OK" if finish_reason != "error" else "ERROR"
        return self.record(
            TraceEventType.LLM_RAW_RESPONSE,
            source,
            f"LLM RESPONSE <- {model}",
            data=data,
            duration_ms=latency_ms,
            status=status,
        )

    def record_thinking(
        self, source: str, model: str, thinking_content: str, thinking_type: str = "reasoning"
    ) -> DevTraceEvent:
        """Record LLM thinking/reasoning content separately for deep analysis."""
        data = {
            "model": model,
            "thinking": thinking_content[:20000] if thinking_content else "",
            "thinking_truncated": len(thinking_content) > 20000 if thinking_content else False,
            "thinking_type": thinking_type,
            "thinking_length": len(thinking_content) if thinking_content else 0,
        }
        return self.record(
            TraceEventType.LLM_THINKING, source, f"THINKING ({thinking_type})", data=data
        )

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

    def _format_event_markdown(self, idx: int, e: DevTraceEvent) -> list[str]:
        """Format an individual trace event into clean, professional Markdown."""
        lines = [
            f"### Event {idx}: `{e.event_type.value}` ─ {e.action}",
            f"- **Source**: `{e.source}` | **Status**: {e.status} | **Latency**: {e.duration_ms:.2f}ms",
        ]

        if not e.data:
            lines.append("")
            return lines

        data = e.data
        if e.event_type == TraceEventType.PROMPT_ENHANCED:
            lines.append(f"- **Goal**: {data.get('intent', 'N/A')}")
            if data.get("targets"):
                lines.append(f"- **Targets**: {', '.join(data.get('targets', []))}")
            if data.get("improvements"):
                lines.append(f"- **Improvements**: {', '.join(data.get('improvements', []))}")
            if data.get("enhanced_prompt"):
                lines.append(
                    "\n<details><summary>Enhanced Prompt Content</summary>\n\n```text\n"
                    + str(data.get("enhanced_prompt", ""))
                    + "\n```\n</details>"
                )
        elif e.event_type == TraceEventType.LLM_RAW_REQUEST:
            lines.append(f"- **Model**: `{data.get('model', 'unknown')}`")
            lines.append(
                f"- **Messages Count**: {data.get('messages_count', len(data.get('messages', [])))}"
            )
            lines.append(f"- **Tools Provided**: {data.get('tools_count', 0)}")
            msgs = data.get("messages", [])
            last_user = next(
                (m.get("content") for m in reversed(msgs) if m.get("role") == "user"), None
            )
            if last_user:
                preview = (
                    str(last_user)[:250] + "..." if len(str(last_user)) > 250 else str(last_user)
                )
                lines.append(f"- **Last User Input**: {preview}")
        elif e.event_type == TraceEventType.LLM_RAW_RESPONSE:
            lines.append(f"- **Model**: `{data.get('model', 'unknown')}`")
            usage = data.get("usage", {})
            lines.append(
                f"- **Tokens**: {usage.get('tokens_in', 0):,} in, {usage.get('tokens_out', 0):,} out"
            )
            resp = str(data.get("response_content", ""))
            if resp:
                resp_preview = resp[:300] + "..." if len(resp) > 300 else resp
                lines.append(f"- **Response Summary**: {resp_preview}")
            if data.get("thinking"):
                lines.append(
                    "\n<details><summary>Model Reasoning / Thinking</summary>\n\n"
                    + str(data.get("thinking", ""))
                    + "\n</details>"
                )
        elif e.event_type == TraceEventType.TOOL_DISPATCH:
            lines.append(f"- **Tool**: `{data.get('tool_name', 'tool')}`")
            if data.get("arguments"):
                lines.append(f"- **Arguments**: `{json.dumps(data.get('arguments', {}))}`")
        else:
            kv_items = [
                f"- **{k}**: `{v}`"
                for k, v in data.items()
                if not isinstance(v, (dict, list)) and len(str(v)) < 120
            ]
            if kv_items:
                lines.extend(kv_items)

        # Place raw JSON in a collapsible block so it never clutters the document
        lines.append(
            "\n<details><summary>View Raw Payload</summary>\n\n```json\n"
            + json.dumps(data, indent=2, default=str)
            + "\n```\n</details>\n"
        )
        return lines

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
                    "## Interaction Graph (Mermaid Flowchart)",
                    mermaid_graph,
                    "",
                    "## Call Hierarchy Map",
                    ascii_tree,
                    "",
                    "## Event Summary",
                    "| Timestamp | Type | Source | Action | Status | Latency |",
                    "| :--- | :--- | :--- | :--- | :--- | :--- |",
                ]
                for e in events:
                    t_str = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                    dur = f"{e.duration_ms:.1f}ms" if e.duration_ms > 0 else "-"
                    lines.append(
                        f"| {t_str} | `{e.event_type.value}` | `{e.source}` | `{e.action}` | {e.status} | {dur} |"
                    )

                lines.append("\n## Detailed Event Trace Log\n")
                for idx, e in enumerate(events, 1):
                    lines.extend(self._format_event_markdown(idx, e))

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


def get_tracer() -> DevTracer:
    """Alias for get_dev_tracer() — backward compatibility."""
    return get_dev_tracer()


def export_session_dev_artifacts(
    session_id: str,
    messages: list[dict[str, Any]],
    cwd: str | Path | None = None,
) -> dict[str, str]:
    """Export chat_export.md, trace.md, and trace.json to project-specific .sago/data/<session_id>/."""
    import re

    project_root = Path(cwd) if cwd else Path.cwd()
    data_dir = project_root / ".sago" / "data" / session_id
    data_dir.mkdir(parents=True, exist_ok=True)

    created_files: dict[str, str] = {}

    # Extract distinct agents involved in session
    agents_involved = sorted({msg.get("agent_name") for msg in messages if msg.get("agent_name")})
    agents_summary = ", ".join(f"`@{a}`" for a in agents_involved) if agents_involved else "`@sago`"

    # 1. Generate rich chat_export.md
    chat_file = data_dir / "chat_export.md"
    chat_lines = [
        "# 💬 SAGO Session Transcript Export",
        f"- **Session ID**: `{session_id}`",
        f"- **Export Timestamp**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Total Messages**: {len(messages)}",
        f"- **Engaged Agents**: {agents_summary}",
        "",
        "---",
        "",
    ]
    for idx, msg in enumerate(messages, 1):
        role = msg.get("role", "unknown").upper()
        agent = msg.get("agent_name", "")
        content = msg.get("content", "")
        t_stamp = msg.get("timestamp")
        time_str = f" • {time.strftime('%H:%M:%S', time.localtime(t_stamp))}" if t_stamp else ""
        agent_tag = f" (Agent: `@{agent}`)" if agent else ""

        chat_lines.append(f"### Turn {idx}: {role}{agent_tag}{time_str}\n")

        # Format reasoning / thinking process
        thinking_match = re.search(
            r"<(?:thinking|thought)>(.*?)</(?:thinking|thought)>", content, re.DOTALL
        )
        body = content
        if thinking_match:
            thinking_text = thinking_match.group(1).strip()
            if thinking_text:
                chat_lines.append(
                    "<details>\n<summary>🧠 <b>Technical Reasoning & Architectural Analysis</b></summary>\n\n"
                )
                chat_lines.append(thinking_text)
                chat_lines.append("\n\n</details>\n")
            body = re.sub(
                r"<(?:thinking|thought)>.*?</(?:thinking|thought)>", "", content, flags=re.DOTALL
            ).strip()

        chat_lines.append(body)
        chat_lines.append("\n\n---\n")

    chat_file.write_text("\n".join(chat_lines), encoding="utf-8")
    created_files["chat_export"] = str(chat_file.resolve())

    # 2. Export trace.md and trace.json
    tracer = get_dev_tracer()
    trace_md_file = data_dir / "trace.md"
    trace_json_file = data_dir / "trace.json"

    ok_md, res_md = tracer.export_traces(trace_md_file, format="md")
    if ok_md:
        created_files["trace_md"] = res_md

    ok_json, res_json = tracer.export_traces(trace_json_file, format="json")
    if ok_json:
        created_files["trace_json"] = res_json

    return created_files
