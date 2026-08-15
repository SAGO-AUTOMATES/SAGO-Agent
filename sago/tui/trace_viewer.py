"""Deep Trace Viewer — Modal popup for analyzing all execution traces.

Shows LLM raw I/O, tool dispatches, agent routing, thinking blocks,
and raw event data in a tabbed, expandable interface.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Static, TabbedContent, TabPane

if TYPE_CHECKING:
    from sago.tracking.dev_tracer import DevTraceEvent


class TraceViewerScreen(ModalScreen[None]):
    """Full-screen modal trace viewer with tabbed sections."""

    CSS = """
    TraceViewerScreen {
        background: $surface;
        align: center middle;
    }
    .trace-viewer-box {
        width: 95%;
        height: 92%;
        border: solid #388bfd;
        background: #0d1117;
        layout: vertical;
    }
    .trace-viewer-header {
        background: #161b22;
        color: #58a6ff;
        padding: 0 1;
        dock: top;
        height: 3;
        align-vertical: middle;
    }
    .trace-viewer-header Static {
        height: 1;
        padding-top: 1;
    }
    .trace-viewer-header Button {
        height: 1;
        min-width: 14;
        margin-right: 1;
    }
    .trace-viewer-tabs {
        dock: top;
        height: 3;
    }
    .trace-tab-content {
        height: 1fr;
        overflow-y: auto;
        padding: 1 2;
    }
    .trace-section {
        margin: 0 0 1 0;
    }
    .trace-section-title {
        color: #58a6ff;
        text-style: bold;
        margin: 1 0 0 0;
    }
    .trace-event {
        padding: 0 1;
        margin: 0 0 0 0;
        border-left: solid #30363d;
    }
    .trace-event:hover {
        border-left: solid #58a6ff;
        background: #161b22;
    }
    .trace-event-expand {
        color: #8b949e;
    }
    .trace-key {
        color: #7ee787;
    }
    .trace-value {
        color: #e6edf3;
    }
    .trace-string {
        color: #c9d1d9;
    }
    .trace-number {
        color: #79c0ff;
    }
    .trace-error {
        color: #f85149;
    }
    .trace-success {
        color: #3fb950;
    }
    .trace-thinking {
        color: #d2a8ff;
        background: #0d1117;
        border-left: solid #d2a8ff;
        padding: 0 1;
        margin: 0 0 0 2;
    }
    .trace-raw-json {
        color: #c9d1d9;
        background: #161b22;
        padding: 1;
        margin: 0 0 0 0;
    }
    .trace-summary-badge {
        color: #f0883e;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
    ]

    def __init__(self, events: list[DevTraceEvent], title: str = "Deep Trace Viewer") -> None:
        super().__init__()
        self.events = events
        self.viewer_title = title

    def compose(self) -> ComposeResult:
        with Vertical(classes="trace-viewer-box"):
            with Horizontal(classes="trace-viewer-header"):
                yield Static(
                    f"[bold]{self.viewer_title}[/bold]  "
                    f"[dim]{len(self.events)} events captured[/dim]",
                )
                yield Static("", classes="spacer")
                yield Button("✕ Close [Esc]", id="btn-close-trace", variant="default")

            with TabbedContent(initial="tab-llm"):
                with TabPane("LLM", id="tab-llm"):
                    yield from self._compose_llm_tab()

                with TabPane("Tools", id="tab-tools"):
                    yield from self._compose_tools_tab()

                with TabPane("Flow", id="tab-flow"):
                    yield from self._compose_flow_tab()

                with TabPane("Thinking", id="tab-thinking"):
                    yield from self._compose_thinking_tab()

                with TabPane("Raw", id="tab-raw"):
                    yield from self._compose_raw_tab()

    @on(Button.Pressed, "#btn-close-trace")
    def on_close_button(self) -> None:
        self.dismiss()

    def _compose_llm_tab(self) -> ComposeResult:
        """Compose the LLM tab showing raw request/response data."""
        with VerticalScroll(classes="trace-tab-content"):
            llm_requests = [e for e in self.events if e.event_type.value == "LLM_RAW_REQUEST"]
            llm_responses = [e for e in self.events if e.event_type.value == "LLM_RAW_RESPONSE"]
            llm_summaries = [e for e in self.events if e.event_type.value == "LLM_PAYLOAD"]

            if not llm_requests and not llm_responses and not llm_summaries:
                yield Static(
                    "[dim]No LLM traces captured. Enable developer mode with /dev on[/dim]"
                )
                return

            yield Static(
                f"[trace-section-title]LLM Invocations ({len(llm_summaries)} calls)[/trace-section-title]"
            )

            # Pair requests and responses by timestamp proximity
            for resp in llm_responses:
                model = resp.data.get("model", "unknown")
                latency = resp.duration_ms
                usage = resp.data.get("usage", {})
                content = resp.data.get("response_content", "")
                tool_calls = resp.data.get("tool_calls", [])
                finish = resp.data.get("finish_reason", "")

                status_cls = "trace-success" if finish != "error" else "trace-error"
                with Vertical(classes="trace-event"):
                    yield Static(
                        f"[{status_cls}]▶[/] [trace-value]{model}[/]  "
                        f"[dim]{latency:.0f}ms  tokens: {usage.get('tokens_in', '?')}→{usage.get('tokens_out', '?')}  "
                        f"finish: {finish}[/]"
                    )
                    if tool_calls:
                        tc_names = ", ".join(tc.get("name", "?") for tc in tool_calls)
                        yield Static(f"  [trace-key]tool_calls:[/] [{len(tool_calls)}] {tc_names}")
                    if content:
                        preview = content[:500].replace("\n", " ")
                        if len(content) > 500:
                            preview += "..."
                        yield Static(f"  [trace-key]response:[/] [trace-string]{preview}[/]")

            # Show raw requests (collapsed by default)
            for req in llm_requests:
                model = req.data.get("model", "unknown")
                msgs = req.data.get("messages", [])
                sys_prompt = req.data.get("system_prompt", "")
                tools_count = req.data.get("tools_count", 0)

                with Vertical(classes="trace-event"):
                    yield Static(
                        f"[trace-key]📤 REQUEST →[/] [trace-value]{model}[/]  "
                        f"[dim]{len(msgs)} messages, {tools_count} tools[/]"
                    )
                    if sys_prompt:
                        preview = sys_prompt[:300].replace("\n", " ")
                        yield Static(f"  [trace-key]system:[/] [trace-string]{preview}[/]")
                    # Show last 2 messages as preview
                    for msg in msgs[-2:]:
                        role = msg.get("role", "?")
                        content = msg.get("content", "")
                        if isinstance(content, str):
                            preview = content[:200].replace("\n", " ")
                        else:
                            preview = str(content)[:200]
                        yield Static(f"  [dim]{role}:[/] [trace-string]{preview}[/]")

    def _compose_tools_tab(self) -> ComposeResult:
        """Compose the Tools tab showing tool dispatches."""
        with VerticalScroll(classes="trace-tab-content"):
            tool_events = [e for e in self.events if e.event_type.value == "TOOL_DISPATCH"]

            if not tool_events:
                yield Static("[dim]No tool traces captured.[/dim]")
                return

            yield Static(
                f"[trace-section-title]Tool Dispatches ({len(tool_events)} calls)[/trace-section-title]"
            )

            for e in tool_events:
                tool_name = e.data.get("tool_name", e.action)
                args = e.data.get("arguments", {})
                result_preview = e.data.get("result_preview", "")
                risk = e.data.get("risk_level", "")
                status_cls = "trace-success" if e.status == "OK" else "trace-error"
                dur = f"{e.duration_ms:.0f}ms" if e.duration_ms > 0 else ""

                with Vertical(classes="trace-event"):
                    yield Static(
                        f"[{status_cls}]{'✓' if e.status == 'OK' else '✗'}[/] "
                        f"[trace-value]{tool_name}[/]  [dim]{dur} {risk}[/]"
                    )
                    if args:
                        args_str = json.dumps(args, default=str)[:300]
                        yield Static(f"  [trace-key]args:[/] [trace-string]{args_str}[/]")
                    if result_preview:
                        yield Static(
                            f"  [trace-key]result:[/] [trace-string]{result_preview[:200]}[/]"
                        )

    def _compose_flow_tab(self) -> ComposeResult:
        """Compose the Flow tab showing execution timeline."""
        with VerticalScroll(classes="trace-tab-content"):
            if not self.events:
                yield Static("[dim]No flow traces captured.[/dim]")
                return

            yield Static("[trace-section-title]Execution Flow[/trace-section-title]")

            # Build timeline
            for e in self.events:
                t_str = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                ms = int((e.timestamp % 1) * 1000)
                time_tag = f"{t_str}.{ms:03d}"
                dur = f" ({e.duration_ms:.1f}ms)" if e.duration_ms > 0 else ""

                # Color by type
                type_colors = {
                    "FUNCTION_CALL": "trace-number",
                    "FUNCTION_RETURN": "trace-number",
                    "LLM_PAYLOAD": "trace-value",
                    "LLM_RAW_REQUEST": "trace-value",
                    "LLM_RAW_RESPONSE": "trace-value",
                    "LLM_THINKING": "trace-thinking",
                    "TOOL_DISPATCH": "trace-success",
                    "AGENT_ROUTING": "trace-summary-badge",
                    "ERROR": "trace-error",
                    "RETRY": "trace-summary-badge",
                    "PERMISSION_CHECK": "trace-number",
                    "LOG_EVENT": "trace-string",
                    "STATE_CHANGE": "trace-string",
                }
                color = type_colors.get(e.event_type.value, "trace-string")
                status_icon = "✓" if e.status == "OK" else "✗"

                with Vertical(classes="trace-event"):
                    yield Static(
                        f"[dim]{time_tag}[/] [{color}]{e.event_type.value}[/] "
                        f"[trace-value]{e.source}[/] → {e.action}{dur} "
                        f"[dim]{status_icon}[/]"
                    )

    def _compose_thinking_tab(self) -> ComposeResult:
        """Compose the Thinking tab showing LLM reasoning blocks."""
        with VerticalScroll(classes="trace-tab-content"):
            thinking_events = [e for e in self.events if e.event_type.value == "LLM_THINKING"]

            # Also extract thinking from LLM responses
            responses = [e for e in self.events if e.event_type.value == "LLM_RAW_RESPONSE"]
            thinking_from_responses = []
            for resp in responses:
                thinking = resp.data.get("thinking", "")
                if thinking:
                    thinking_from_responses.append((resp, thinking))

            if not thinking_events and not thinking_from_responses:
                yield Static(
                    "[dim]No thinking traces captured. LLM thinking blocks will appear here.[/dim]"
                )
                return

            if thinking_events:
                yield Static(
                    f"[trace-section-title]Thinking Blocks ({len(thinking_events)} entries)[/trace-section-title]"
                )
                for e in thinking_events:
                    thinking = e.data.get("thinking", "")
                    model = e.data.get("model", "")
                    thinking_type = e.data.get("thinking_type", "reasoning")
                    t_len = e.data.get("thinking_length", len(thinking))

                    with Vertical(classes="trace-event"):
                        yield Static(
                            f"[trace-key]💭 {thinking_type}[/] [dim]{model} ({t_len} chars)[/]"
                        )
                        # Show thinking content in a styled block
                        for line in thinking[:5000].split("\n"):
                            yield Static(f"  [trace-thinking]{line}[/]")
                        if len(thinking) > 5000:
                            yield Static(f"  [dim]... ({len(thinking) - 5000} more chars)[/]")

            if thinking_from_responses:
                yield Static(
                    f"[trace-section-title]Thinking from Responses ({len(thinking_from_responses)})[/trace-section-title]"
                )
                for resp, thinking in thinking_from_responses:
                    model = resp.data.get("model", "")
                    with Vertical(classes="trace-event"):
                        yield Static(
                            f"[trace-key]💭 response thinking[/] [dim]{model} ({len(thinking)} chars)[/]"
                        )
                        for line in thinking[:5000].split("\n"):
                            yield Static(f"  [trace-thinking]{line}[/]")
                        if len(thinking) > 5000:
                            yield Static(f"  [dim]... ({len(thinking) - 5000} more chars)[/]")

    def _compose_raw_tab(self) -> ComposeResult:
        """Compose the Raw tab showing full JSON event data."""
        with VerticalScroll(classes="trace-tab-content"):
            if not self.events:
                yield Static("[dim]No raw events captured.[/dim]")
                return

            yield Static(
                f"[trace-section-title]All Events ({len(self.events)} total)[/trace-section-title]"
            )

            for idx, e in enumerate(self.events):
                t_str = time.strftime("%H:%M:%S", time.localtime(e.timestamp))
                ms = int((e.timestamp % 1) * 1000)
                time_tag = f"{t_str}.{ms:03d}"

                with Vertical(classes="trace-event"):
                    yield Static(
                        f"[trace-key]Event {idx + 1}[/] [dim]{time_tag}[/] "
                        f"[trace-value]{e.event_type.value}[/] {e.source} → {e.action}"
                    )
                    if e.data:
                        # Format JSON with syntax highlighting
                        json_str = json.dumps(e.data, indent=2, default=str)
                        # Simple syntax highlighting
                        for line in json_str.split("\n")[:50]:  # Limit to 50 lines per event
                            yield Static(f"  [trace-raw-json]{line}[/]")
                        if len(json_str.split("\n")) > 50:
                            yield Static(
                                f"  [dim]... ({len(json_str.split(chr(10))) - 50} more lines)[/]"
                            )

    def action_close(self) -> None:
        """Close the trace viewer."""
        self.dismiss()
