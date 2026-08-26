"""Deep Trace & Dev Console — Interactive execution inspector and telemetry viewer.

Features:
 - 7 tabs: Overview · LLM · Tools · Flow · Graph · Thinking · Events
 - Per-event human-readable formatting without markup injection or truncation
 - Complete untruncated expandable views
 - Visual ASCII interaction graph for agent handoffs and tool executions
 - Rich export options (JSON / Markdown / Full dump)
 - Clipboard copy with system fallback
 - Keyboard shortcuts: Esc/q close, e export, c copy, Tab switch tabs
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

from rich.markup import escape
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Collapsible, Label, Static, TabbedContent, TabPane

if TYPE_CHECKING:
    from sago.tracking.dev_tracer import DevTraceEvent


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _fmt_ms(ms: float) -> str:
    if ms <= 0:
        return ""
    if ms < 1000:
        return f"{ms:.0f}ms"
    return f"{ms / 1000:.2f}s"


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.") + f"{int((ts % 1) * 1000):03d}"


def _fmt_kv(data: dict, max_value: int = 400) -> list[str]:
    """Format dict keys/values cleanly without JSON blobs and without markup errors."""
    lines = []
    for k, v in data.items():
        if isinstance(v, list):
            if len(v) == 0:
                lines.append(f"  {k}: (empty)")
            elif len(v) <= 3:
                items_str = ", ".join(str(i)[:120] for i in v)
                lines.append(f"  {k}: [{items_str}]")
            else:
                lines.append(f"  {k}: [{len(v)} items] {str(v[0])[:100]}…")
        elif isinstance(v, dict):
            if len(v) == 0:
                lines.append(f"  {k}: {{empty}}")
            else:
                inner = ", ".join(f"{ki}: {str(vi)[:60]}" for ki, vi in list(v.items())[:6])
                lines.append(f"  {k}: {{ {inner} }}")
        elif isinstance(v, str):
            preview = v.replace("\n", " ").strip()
            if len(preview) > max_value:
                preview = preview[:max_value] + "…"
            lines.append(f"  {k}: {preview}")
        elif isinstance(v, bool):
            lines.append(f"  {k}: {'yes' if v else 'no'}")
        else:
            lines.append(f"  {k}: {v}")
    return lines


TYPE_ICONS: dict[str, tuple[str, str]] = {
    "LLM_RAW_REQUEST": ("📤", "request"),
    "LLM_RAW_RESPONSE": ("📥", "response"),
    "LLM_PAYLOAD": ("🧠", "llm"),
    "LLM_THINKING": ("💭", "thinking"),
    "TOOL_DISPATCH": ("🔧", "tool"),
    "AGENT_ROUTING": ("🔀", "routing"),
    "FUNCTION_CALL": ("📞", "fn-call"),
    "FUNCTION_RETURN": ("↩", "fn-return"),
    "ERROR": ("❌", "error"),
    "RETRY": ("🔁", "retry"),
    "PERMISSION_CHECK": ("🔒", "perm"),
    "LOG_EVENT": ("📝", "log"),
    "STATE_CHANGE": ("🔄", "state"),
}

_TV_CSS = """
TraceViewerScreen {
    background: rgba(0,0,0,0.85);
    align: center middle;
}
.tv-box {
    width: 96%;
    height: 94%;
    background: #0d1117;
    border: none;
    layout: vertical;
}
.tv-header {
    height: auto;
    min-height: 3;
    background: #161b22;
    border-top: solid #388bfd;
    border-bottom: solid #21262d;
    padding: 0 2;
    layout: horizontal;
}
.tv-title {
    color: #58a6ff;
    text-style: bold;
    width: auto;
    min-width: 12;
    height: auto;
    content-align: left middle;
}
.tv-stats {
    color: #8b949e;
    height: auto;
    content-align: left middle;
    margin-right: 2;
    text-wrap: wrap;
}
.tv-btn {
    height: 1;
    min-width: 12;
    margin-left: 1;
    border: none;
    background: #21262d;
    color: #8b949e;
}
.tv-btn:hover {
    background: #30363d;
    color: #e6edf3;
}
.tv-btn-export { color: #f0883e; }
.tv-btn-export:hover { background: #2d1f0e; color: #f0883e; }
.tv-btn-close  { color: #f85149; }
.tv-btn-close:hover  { background: #1f0e0e; color: #f85149; }
.tv-shortcuts {
    height: 1;
    background: #0d1117;
    border-bottom: solid #21262d;
    padding: 0 2;
    align-vertical: middle;
    color: #484f58;
}
TabbedContent { height: 1fr; background: #0d1117; }
TabPane       { background: #0d1117; padding: 0; }
.tv-tab-scroll { height: 1fr; padding: 1 2; }
.tv-section-head {
    color: #388bfd;
    text-style: bold;
    margin: 1 0 0 0;
    padding: 0 1;
    border-left: solid #388bfd;
}
.tv-empty { color: #484f58; padding: 2 2; }
.tv-event {
    border-left: solid #30363d;
    background: #0d1117;
    margin: 0 0 1 0;
    padding: 0 0 0 1;
}
.tv-event:hover { border-left: solid #388bfd; background: #161b22; }
.tv-event-key { color: #7ee787; }
.tv-event-val { color: #c9d1d9; }
.tv-event-dimval { color: #8b949e; }
.tv-ok    { color: #3fb950; }
.tv-err   { color: #f85149; }
.tv-warn  { color: #d29922; }
.tv-llm   { color: #79c0ff; }
.tv-tool  { color: #56d364; }
.tv-route { color: #f0883e; }
.tv-think { color: #d2a8ff; }
.tv-thinking-block {
    background: #12091f;
    border-left: solid #7139ba;
    padding: 0 2;
    color: #d2a8ff;
}
.tv-response-block {
    background: #091520;
    border-left: solid #1f6feb;
    padding: 0 2;
    color: #e6edf3;
}
.tv-graph-block {
    background: #080c14;
    border: solid #21262d;
    border-left: solid #58a6ff;
    padding: 1 2;
    margin: 1 0;
    color: #79c0ff;
}
.tv-stat-row { height: 5; margin: 1 0; overflow-x: auto; }
.tv-stat-box {
    width: 1fr; height: 5;
    min-width: 10;
    background: #161b22;
    border: solid #21262d;
    align: center middle;
    margin: 0 1;
}
.tv-stat-num   { text-style: bold; height: 2; content-align: center middle; }
.tv-stat-label { color: #8b949e; height: 1; content-align: center middle; }
.tv-timeline-row { height: 1; padding: 0 1; color: #8b949e; }
.tv-timeline-row:hover { background: #161b22; color: #e6edf3; }
.tv-export-note {
    height: 1; dock: bottom;
    background: #1f4c1f; color: #3fb950;
    padding: 0 2; display: none;
}
.tv-export-note.visible { display: block; }
"""


class TraceViewerScreen(ModalScreen[None]):
    """Modern full-screen developer console and execution inspector modal."""

    CSS = _TV_CSS

    BINDINGS = [
        Binding("escape", "close_viewer", "Close"),
        Binding("q", "close_viewer", "Close"),
        Binding("e", "export_trace", "Export"),
        Binding("c", "copy_trace", "Copy"),
    ]

    def __init__(
        self,
        events: list[DevTraceEvent],
        title: str = "Inspector",
        turn_label: str = "",
    ) -> None:
        super().__init__()
        self.events = events
        self.viewer_title = title
        self.turn_label = turn_label

    def compose(self) -> ComposeResult:
        ev = self.events
        llm_ev = [e for e in ev if e.event_type.value in ("LLM_RAW_RESPONSE", "LLM_PAYLOAD")]
        tool_ev = [e for e in ev if e.event_type.value == "TOOL_DISPATCH"]
        # Dedupe thinking per-agent, per-step: LLM_THINKING + LLM_RAW_RESPONSE with thinking
        # Include source in key so architect vs python-engineer are distinct, only exact duplicate
        # [:300] from same source is deduped (prevents spam but preserves per-agent distinction)
        _seen_thinking: set[tuple[str, str]] = set()
        think_ev: list = []
        for e in ev:
            if e.event_type.value == "LLM_THINKING":
                t = (e.data.get("thinking") or "").strip()
                # Use source + first 300 chars as dedupe key (per-agent distinct)
                _src = str(e.source or "")
                key = (_src, t[:300] if t else str(e.timestamp))
                if key not in _seen_thinking:
                    _seen_thinking.add(key)
                    think_ev.append(e)
            elif e.event_type.value == "LLM_RAW_RESPONSE" and e.data.get("thinking"):
                t = (e.data.get("thinking") or "").strip()
                _src = str(e.source or "")
                key = (_src, t[:300] if t else str(e.timestamp))
                if key not in _seen_thinking:
                    _seen_thinking.add(key)
                    think_ev.append(e)
        err_ev = [e for e in ev if e.event_type.value == "ERROR" or e.status in ("ERROR", "FAILED")]
        route_ev = [e for e in ev if e.event_type.value == "AGENT_ROUTING"]

        subtitle = self.turn_label or f"{len(ev)} events"

        with Vertical(classes="tv-box"):
            with Horizontal(classes="tv-header"):
                yield Label(
                    f"⚡ {escape(self.viewer_title)}  [dim]{escape(subtitle)}[/dim]",
                    classes="tv-title",
                    markup=True,
                )
                yield Label(
                    f"[bold cyan]{len(llm_ev)}[/] LLM  "
                    f"[bold green]{len(tool_ev)}[/] tools  "
                    f"[bold yellow]{len(think_ev)}[/] thinking  "
                    f"[bold red]{len(err_ev)}[/] errors",
                    classes="tv-stats",
                    markup=True,
                )
                yield Button("⬆ Export", id="btn-tv-export", classes="tv-btn tv-btn-export")
                yield Button("⎘ Copy", id="btn-tv-copy", classes="tv-btn")
                yield Button("✕ Close", id="btn-tv-close", classes="tv-btn tv-btn-close")

            yield Static(
                "[dim]Esc / q[/] close  [dim]e[/] export  [dim]c[/] copy  [dim]Tab[/] switch tabs",
                classes="tv-shortcuts",
                markup=True,
            )

            with TabbedContent(initial="tab-overview"):
                with TabPane("Overview", id="tab-overview"):
                    yield from self._tab_overview(llm_ev, tool_ev, route_ev, think_ev, err_ev)
                with TabPane("LLM", id="tab-llm"):
                    yield from self._tab_llm()
                with TabPane("Tools", id="tab-tools"):
                    yield from self._tab_tools()
                with TabPane("Flow", id="tab-flow"):
                    yield from self._tab_flow()
                with TabPane("Event Graph", id="tab-graph"):
                    yield from self._tab_graph()
                with TabPane("Thinking", id="tab-thinking"):
                    yield from self._tab_thinking()
                with TabPane("Events", id="tab-events"):
                    yield from self._tab_events()

            yield Static("", id="tv-export-note", classes="tv-export-note")

    # ── Overview ─────────────────────────────────────────────────────────────

    def _tab_overview(self, llm_ev, tool_ev, route_ev, think_ev, err_ev) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            with Horizontal(classes="tv-stat-row"):
                with Vertical(classes="tv-stat-box"):
                    yield Label(str(len(self.events)), classes="tv-stat-num tv-llm")
                    yield Label("events", classes="tv-stat-label")
                with Vertical(classes="tv-stat-box"):
                    yield Label(str(len(llm_ev)), classes="tv-stat-num tv-llm")
                    yield Label("LLM calls", classes="tv-stat-label")
                with Vertical(classes="tv-stat-box"):
                    yield Label(str(len(tool_ev)), classes="tv-stat-num tv-tool")
                    yield Label("tool calls", classes="tv-stat-label")
                with Vertical(classes="tv-stat-box"):
                    yield Label(str(len(think_ev)), classes="tv-stat-num tv-think")
                    yield Label("thinking", classes="tv-stat-label")
                with Vertical(classes="tv-stat-box"):
                    yield Label(str(len(err_ev)), classes="tv-stat-num tv-err")
                    yield Label("errors", classes="tv-stat-label")

            if self.events:
                s_ts = self.events[0].timestamp
                e_ts = self.events[-1].timestamp
                wall = _fmt_ms((e_ts - s_ts) * 1000)
                llm_t = sum(e.duration_ms for e in llm_ev if e.duration_ms > 0)
                tool_t = sum(e.duration_ms for e in tool_ev if e.duration_ms > 0)
                tok_in = sum(
                    e.data.get("tokens_in", e.data.get("usage", {}).get("tokens_in", 0))
                    for e in llm_ev
                )
                tok_out = sum(
                    e.data.get("tokens_out", e.data.get("usage", {}).get("tokens_out", 0))
                    for e in llm_ev
                )
                em_dash = "—"
                yield Label("Session Timing & Metrics", classes="tv-section-head")
                yield Static(
                    f"  [dim]Start[/]        {_fmt_ts(s_ts)}\n"
                    f"  [dim]End[/]          {_fmt_ts(e_ts)}\n"
                    f"  [dim]Wall time[/]     {wall or 'instant'}\n"
                    f"  [dim]LLM time[/]      {_fmt_ms(llm_t) or em_dash}\n"
                    f"  [dim]Tool time[/]     {_fmt_ms(tool_t) or em_dash}\n"
                    f"  [dim]Tokens in[/]     {tok_in or em_dash}\n"
                    f"  [dim]Tokens out[/]    {tok_out or em_dash}",
                    markup=True,
                )

            if tool_ev:
                yield Label("Tools Called", classes="tv-section-head")
                for e in tool_ev:
                    name = e.data.get("tool_name", e.action)
                    ok = e.status == "OK"
                    yield Static(
                        f"  [{'tv-ok' if ok else 'tv-err'}]{'✓' if ok else '✗'}[/] "
                        f"[bold]{escape(str(name))}[/]  [dim]{_fmt_ms(e.duration_ms)}[/]",
                        markup=True,
                    )

            if err_ev:
                yield Label("Errors & Failures", classes="tv-section-head")
                for e in err_ev:
                    msg = e.data.get("error", e.data.get("message", e.action))
                    yield Static(
                        f"  [bold red]✗[/] [dim]{escape(e.event_type.value)}[/]  {escape(str(msg)[:160])}",
                        markup=True,
                    )

    # ── LLM tab ──────────────────────────────────────────────────────────────

    def _tab_llm(self) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            llm_resp = [e for e in self.events if e.event_type.value == "LLM_RAW_RESPONSE"]
            llm_req = [e for e in self.events if e.event_type.value == "LLM_RAW_REQUEST"]
            llm_pay = [e for e in self.events if e.event_type.value == "LLM_PAYLOAD"]
            if not llm_resp and not llm_req and not llm_pay:
                yield Static(
                    "  [dim]No LLM traces yet. Enable developer mode with [bold]/dev on[/bold][/]",
                    classes="tv-empty",
                    markup=True,
                )
                return

            used_req: set[int] = set()
            pairs: list[tuple] = []
            for resp in llm_resp:
                best_req = None
                best_diff = float("inf")
                for req in llm_req:
                    if id(req) in used_req:
                        continue
                    diff = abs(resp.timestamp - req.timestamp)
                    if diff < best_diff:
                        best_diff = diff
                        best_req = req
                if best_req and best_diff < 120:
                    pairs.append((best_req, resp))
                    used_req.add(id(best_req))
                else:
                    pairs.append((None, resp))

            for req, resp in pairs:
                model = resp.data.get("model", "unknown")
                latency = _fmt_ms(resp.duration_ms)
                usage = resp.data.get("usage", {})
                tok_in = usage.get("tokens_in", req.data.get("messages_count", "?") if req else "?")
                tok_out = usage.get("tokens_out", "?")
                finish = resp.data.get("finish_reason", "")
                tcalls = resp.data.get("tool_calls", [])
                content = resp.data.get("response_content", "")
                is_ok = finish not in ("error", "stop_error") and resp.status != "ERROR"
                ts = _fmt_ts(resp.timestamp)

                with Collapsible(
                    title=f"{'✓' if is_ok else '✗'} {escape(str(model))}  {latency}  {ts}  tok: {tok_in}→{tok_out}",
                    collapsed=False,
                ):
                    if req:
                        msgs = req.data.get("messages", [])
                        tools_n = req.data.get("tools_count", 0)
                        yield Static(
                            f"  [dim]Request:[/] {len(msgs)} messages in context, {tools_n} tools declared",
                            markup=True,
                        )
                        for msg in msgs[-3:]:
                            role = msg.get("role", "?")
                            mc = msg.get("content", "")
                            if isinstance(mc, list):
                                mc = " ".join(p.get("text", "") for p in mc if isinstance(p, dict))
                            preview = str(mc).replace("\n", " ")[:300]
                            rc = (
                                "tv-llm"
                                if role == "assistant"
                                else "tv-tool"
                                if role == "tool"
                                else "tv-event-val"
                            )
                            yield Static(
                                f"  [{rc}]{escape(str(role))}[/]  {escape(preview)}", markup=True
                            )

                    if tcalls:
                        yield Static(
                            f"  [bold green]Tool calls generated ({len(tcalls)})[/]", markup=True
                        )
                        for tc in tcalls:
                            tname = tc.get("name", "?")
                            targs = tc.get("args", {})
                            if isinstance(targs, dict):
                                ap = ", ".join(
                                    f"{k}={str(v)[:60]}" for k, v in list(targs.items())[:4]
                                )
                            else:
                                ap = str(targs)[:120]
                            yield Static(
                                f"  [bold cyan]  → {escape(str(tname))}[/]  [dim]{escape(ap)}[/]",
                                markup=True,
                            )

                    if content:
                        with Collapsible(title="Assistant response text", collapsed=False):
                            yield Static(content, classes="tv-response-block", markup=False)

    # ── Tools tab ────────────────────────────────────────────────────────────

    def _tab_tools(self) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            tool_ev = [e for e in self.events if e.event_type.value == "TOOL_DISPATCH"]
            if not tool_ev:
                yield Static("  [dim]No tool calls recorded.[/]", classes="tv-empty", markup=True)
                return

            ok_n = sum(1 for e in tool_ev if e.status == "OK")
            fail_n = len(tool_ev) - ok_n
            yield Static(
                f"  [bold green]{ok_n} ok[/]  [bold red]{fail_n} failed[/]  [dim]/ {len(tool_ev)} total calls[/]",
                markup=True,
            )

            for idx, e in enumerate(tool_ev, 1):
                name = e.data.get("tool_name", e.action)
                args = e.data.get("arguments", {})
                result = e.data.get("result_preview", e.data.get("result", ""))
                risk = e.data.get("risk_level", "")
                dur = _fmt_ms(e.duration_ms)
                ts = _fmt_ts(e.timestamp)
                is_ok = e.status == "OK"

                with Collapsible(
                    title=f"{'✓' if is_ok else '✗'} [{idx}] {escape(str(name))}  {dur}  {ts}  {risk}",
                    collapsed=(idx > 4),
                ):
                    if isinstance(args, dict) and args:
                        yield Static("  [dim]Arguments:[/]", markup=True)
                        for line in _fmt_kv(args):
                            k, _, v = line.partition(":")
                            yield Static(
                                f"  [tv-event-key]{escape(k.strip())}[/] [dim]→[/] {escape(v.strip())}",
                                markup=True,
                            )
                    elif args:
                        yield Static(f"  [dim]args:[/] {escape(str(args)[:300])}", markup=True)

                    if result:
                        with Collapsible(title="Tool Execution Output", collapsed=False):
                            yield Static(str(result), classes="tv-response-block", markup=False)

                    if not is_ok and e.data.get("error"):
                        yield Static(
                            f"  [bold red]Error:[/] {escape(str(e.data['error'])[:300])}",
                            markup=True,
                        )

    # ── Flow tab ─────────────────────────────────────────────────────────────

    def _tab_flow(self) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            if not self.events:
                yield Static("  [dim]No events.[/]", classes="tv-empty", markup=True)
                return

            COLOR_MAP = {
                "LLM_RAW_REQUEST": "tv-llm",
                "LLM_RAW_RESPONSE": "tv-llm",
                "LLM_PAYLOAD": "tv-llm",
                "LLM_THINKING": "tv-think",
                "TOOL_DISPATCH": "tv-tool",
                "AGENT_ROUTING": "tv-route",
                "ERROR": "tv-err",
                "RETRY": "tv-warn",
                "PERMISSION_CHECK": "tv-warn",
            }
            prev = self.events[0].timestamp
            for e in self.events:
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("·", ""))
                color = COLOR_MAP.get(e.event_type.value, "tv-event-dimval")
                ts = _fmt_ts(e.timestamp)
                dur = _fmt_ms(e.duration_ms)
                gap = _fmt_ms((e.timestamp - prev) * 1000)
                gap_s = f"[dim]+{gap}[/] " if gap else ""
                sicon = (
                    "✓" if e.status == "OK" else ("✗" if e.status in ("ERROR", "FAILED") else " ")
                )
                prev = e.timestamp

                al = e.action
                if e.event_type.value == "TOOL_DISPATCH":
                    al = e.data.get("tool_name", e.action)
                elif "LLM" in e.event_type.value:
                    al = e.data.get("model", e.action)

                yield Static(
                    f"  [dim]{ts}[/] {gap_s}[{color}]{icon} {escape(e.event_type.value)}[/]  "
                    f"[bold]{escape(str(al)[:50])}[/]  [dim]{dur}[/]  {sicon}",
                    classes="tv-timeline-row",
                    markup=True,
                )

    # ── Event Graph tab ──────────────────────────────────────────────────────

    def _tab_graph(self) -> ComposeResult:
        """Visual interaction graph showing orchestration flow."""
        with VerticalScroll(classes="tv-tab-scroll"):
            if not self.events:
                yield Static(
                    "  [dim]No interaction events captured.[/]", classes="tv-empty", markup=True
                )
                return

            # Simplified flow: 1 line per step, no deep nesting, deduped reasoning
            graph_lines = [
                "SAGO Flow  •  User → LLM → Tools → Response",
                "",
                "● User turn started",
            ]

            step_idx = 1
            seen_thinking: set[str] = set()
            for e in self.events:
                et = e.event_type.value
                dur = f" ({_fmt_ms(e.duration_ms)})" if e.duration_ms > 0 else ""
                status_mark = "✓" if e.status == "OK" else "✗"

                if et in ("LLM_PAYLOAD", "LLM_RAW_REQUEST", "LLM_RAW_RESPONSE"):
                    model = e.data.get("model", "LLM")
                    # Only show one LLM step per logical call (payload/request/response are same)
                    # Dedupe by step_idx timing — skip near-duplicate LLM events within 1s
                    if graph_lines and f"LLM → {model}" in graph_lines[-1]:
                        continue
                    tokens_in = e.data.get("tokens_in", e.data.get("usage", {}).get("tokens_in", 0))
                    tokens_out = e.data.get(
                        "tokens_out", e.data.get("usage", {}).get("tokens_out", 0)
                    )
                    tok_str = (
                        f"  In:{tokens_in} Out:{tokens_out}" if tokens_in or tokens_out else ""
                    )
                    graph_lines.append(f"{step_idx}. LLM → {model}{tok_str}{dur}")
                    # Inline single reasoning if present (not separate step, avoids duplicate)
                    t = (e.data.get("thinking") or "").strip()
                    if t:
                        key = t[:200]
                        if key not in seen_thinking:
                            seen_thinking.add(key)
                            preview = t.splitlines()[0][:80].replace('"', "'")
                            graph_lines.append(f'   ↳ reasoning: "{preview}..."')
                    step_idx += 1
                elif et == "LLM_THINKING":
                    # Show as indented sub-item, not a numbered step — avoids duplicate 2,6,8
                    t = (e.data.get("thinking") or "").strip()
                    key = t[:200] if t else ""
                    if key and key in seen_thinking:
                        continue
                    if key:
                        seen_thinking.add(key)
                    preview = t.splitlines()[0][:80].replace('"', "'") if t else "thinking"
                    graph_lines.append(f'   ↳ reasoning: "{preview}..."')
                    # No step_idx increment — reasoning is sub-step of previous LLM
                elif et == "TOOL_DISPATCH":
                    tname = e.data.get("tool_name", e.action)
                    # Break clearly on ask_question
                    if tname == "ask_question":
                        args = e.data.get("arguments", {})
                        q_text = ""
                        if isinstance(args, dict):
                            # questions may be list or JSON string
                            qs = args.get("questions", "")
                            if isinstance(qs, list) and qs:
                                first = qs[0]
                                if isinstance(first, dict):
                                    q_text = first.get("question", "") or str(first)
                                else:
                                    q_text = str(first)
                            elif isinstance(qs, str):
                                q_text = qs
                            else:
                                q_text = str(qs)[:60]
                        else:
                            q_text = str(args)[:60]
                        # Clean
                        q_text = q_text.replace("\n", " ").strip()[:60]
                        graph_lines.append(
                            f'{step_idx}. ❓ question: "{q_text}" [{status_mark}]{dur}'
                        )
                    else:
                        args = e.data.get("arguments", {})
                        args_summary = ""
                        if isinstance(args, dict) and args:
                            args_summary = ", ".join(
                                f"{k}={str(v)[:20]}" for k, v in list(args.items())[:2]
                            )
                        args_str = f" ({args_summary})" if args_summary else ""
                        graph_lines.append(
                            f"{step_idx}. tool: {tname}{args_str} [{status_mark}]{dur}"
                        )
                    step_idx += 1
                elif et == "AGENT_ROUTING":
                    target = e.data.get("target_agent", e.action)
                    graph_lines.append(f"{step_idx}. delegate → @{target}")
                    step_idx += 1
                elif et == "ERROR":
                    err_msg = e.data.get("error", e.action)
                    graph_lines.append(f"{step_idx}. ⚠️ {err_msg[:60]}")
                    step_idx += 1

            graph_lines.append("")
            graph_lines.append("● response delivered")

            yield Static("\n".join(graph_lines), classes="tv-graph-block", markup=False)

    # ── Thinking tab ─────────────────────────────────────────────────────────

    def _tab_thinking(self) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            # Show each thinking per turn, per-agent — dedupe only exact duplicate within same turn (5s window)
            # Extract agent from source like "tui.llm.openrouter" or "agent.sago-orchestrator"
            seen: set[tuple[str, str]] = set()
            blocks: list[tuple[str, str, object]] = []
            for e in self.events:
                if e.event_type.value == "LLM_THINKING":
                    t = (e.data.get("thinking") or "").strip()
                    _src = str(e.source or "")
                    key = (_src, t[:300] if t else str(e.timestamp))
                    if key not in seen:
                        seen.add(key)
                        blocks.append((e.data.get("model", ""), t, e))
            for e in self.events:
                if e.event_type.value == "LLM_RAW_RESPONSE":
                    t = (e.data.get("thinking") or "").strip()
                    if t:
                        _src = str(e.source or "")
                        key = (_src, t[:300] if t else str(e.timestamp))
                        if key not in seen:
                            seen.add(key)
                            blocks.append((e.data.get("model", ""), t, e))

            if not blocks:
                yield Static(
                    "  [dim]No thinking / reasoning blocks captured.\n"
                    "  These appear when the LLM produces reasoning or <thinking> blocks.[/]",
                    classes="tv-empty",
                    markup=True,
                )
                return

            for idx, (model, thinking, e) in enumerate(blocks, 1):  # type: ignore[attr-defined]
                ts = _fmt_ts(e.timestamp)  # type: ignore[attr-defined]
                chars = len(thinking)
                lines = thinking.count("\n") + 1
                _src = escape(str(getattr(e, "source", "")))  # type: ignore[attr-defined]
                _agent_label = f"@{_src.replace('agent.', '')}" if "agent." in _src else _src
                with Collapsible(
                    title=f"💭 Block {idx}  {_agent_label}  {escape(str(model))}  {chars:,} chars  {lines} lines  {ts}",
                    collapsed=(idx > 1),
                ):
                    yield Static(thinking, classes="tv-thinking-block", markup=False)

    # ── Events tab ───────────────────────────────────────────────────────────

    def _tab_events(self) -> ComposeResult:
        """Human-readable event log — safe rendering without markup crashes."""
        with VerticalScroll(classes="tv-tab-scroll"):
            if not self.events:
                yield Static("  [dim]No events.[/]", classes="tv-empty", markup=True)
                return

            yield Static(f"  [dim]{len(self.events)} events captured[/]", markup=True)

            for idx, e in enumerate(self.events, 1):
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("·", ""))
                ts = _fmt_ts(e.timestamp)
                dur = _fmt_ms(e.duration_ms)
                is_ok = e.status in ("OK", "")
                scls = "tv-ok" if is_ok else "tv-err"
                sicon = "✓" if is_ok else "✗"

                with Collapsible(
                    title=f"{icon} [{idx}] {escape(e.event_type.value)}  {escape(str(e.source))}  {dur}  {ts}  {sicon}",
                    collapsed=True,
                ):
                    yield Static(f"  [dim]source:[/] {escape(str(e.source))}", markup=True)
                    yield Static(f"  [dim]action:[/] {escape(str(e.action))}", markup=True)
                    yield Static(
                        f"  [dim]status:[/] [{scls}]{escape(str(e.status or 'ok'))}[/]", markup=True
                    )
                    if dur:
                        yield Static(f"  [dim]duration:[/] {dur}", markup=True)
                    if e.data:
                        yield Static("  [dim]data:[/]", markup=True)
                        for line in _fmt_kv(e.data, max_value=250):
                            k, _, v = line.partition(":")
                            yield Static(
                                f"  [tv-event-key]{escape(k.strip())}[/] [dim]→[/] {escape(v.strip())}",
                                markup=True,
                            )
                        # Untruncated data drawer
                        with Collapsible(title="Raw Data (Full View)", collapsed=True):
                            raw_json = json.dumps(e.data, indent=2, default=str)
                            yield Static(raw_json, classes="tv-response-block", markup=False)

    # ── Button handlers ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-tv-close")
    def _on_close_btn(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#btn-tv-export")
    def _on_export_btn(self) -> None:
        self.action_export_trace()

    @on(Button.Pressed, "#btn-tv-copy")
    def _on_copy_btn(self) -> None:
        self.action_copy_trace()

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_close_viewer(self) -> None:
        self.dismiss()

    def action_close(self) -> None:
        self.dismiss()

    def on_close_button(self) -> None:
        self.dismiss()

    def _show_note(self, msg: str, ok: bool = True) -> None:
        note = self.query_one("#tv-export-note", Static)
        prefix = "✓" if ok else "✗"
        note.update(f"{prefix} {msg}")
        note.add_class("visible")
        self.set_timer(4, lambda: note.remove_class("visible"))

    def action_export_trace(self) -> None:
        """Export trace to JSON + Markdown."""
        try:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = f"sago_trace_{stamp}.json"
            md_path = f"sago_trace_{stamp}.md"

            payload = [
                {
                    "idx": i + 1,
                    "timestamp": e.timestamp,
                    "time": _fmt_ts(e.timestamp),
                    "type": e.event_type.value,
                    "source": e.source,
                    "action": e.action,
                    "status": e.status,
                    "duration_ms": e.duration_ms,
                    "data": e.data,
                }
                for i, e in enumerate(self.events)
            ]
            with open(json_path, "w") as f:
                json.dump(payload, f, indent=2, default=str)

            llm_ev = [e for e in self.events if "LLM" in e.event_type.value]
            tool_ev = [e for e in self.events if e.event_type.value == "TOOL_DISPATCH"]
            md_lines = [
                f"# SAGO Execution Trace — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                f"**Session:** {self.turn_label or 'full session'}  "
                f"**Events:** {len(self.events)}  "
                f"**LLM calls:** {len(llm_ev)}  "
                f"**Tool calls:** {len(tool_ev)}",
                "",
                "## Event Log",
                "",
            ]
            for i, e in enumerate(self.events, 1):
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("·", ""))
                md_lines.append(f"### [{i}] {icon} {e.event_type.value} — {_fmt_ts(e.timestamp)}")
                md_lines.append(f"- **Source:** `{e.source}`")
                md_lines.append(f"- **Action:** `{e.action}`")
                md_lines.append(f"- **Status:** {e.status or 'ok'}")
                if e.duration_ms > 0:
                    md_lines.append(f"- **Duration:** {_fmt_ms(e.duration_ms)}")
                if e.data:
                    md_lines.append("")
                    md_lines.append("```")
                    md_lines.extend(_fmt_kv(e.data, max_value=500))
                    md_lines.append("```")
                md_lines.append("")

            with open(md_path, "w") as f:
                f.write("\n".join(md_lines))

            self._show_note(f"Exported → {json_path}  +  {md_path}", ok=True)
        except Exception as exc:
            self._show_note(f"Export failed: {exc}", ok=False)

    def action_copy_trace(self) -> None:
        """Copy trace summary to clipboard."""
        try:
            lines = [f"SAGO Trace — {len(self.events)} events  {datetime.now().isoformat()}"]
            for i, e in enumerate(self.events, 1):
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("·", ""))
                lines.append(
                    f"[{i}] {icon} {e.event_type.value}  "
                    f"{e.source}  {e.action}  {e.status}  {_fmt_ms(e.duration_ms)}"
                )
            text = "\n".join(lines)

            import subprocess

            for cmd in (
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
                ["pbcopy"],
                ["wl-copy"],
            ):
                try:
                    subprocess.run(
                        cmd, input=text.encode(), timeout=2, check=True, capture_output=True
                    )
                    self._show_note(f"Copied {len(lines)} lines to clipboard", ok=True)
                    return
                except Exception:
                    continue
            raise RuntimeError("No clipboard utility found (xclip/xsel/pbcopy/wl-copy)")
        except Exception as exc:
            self._show_note(f"Copy failed: {exc}", ok=False)
