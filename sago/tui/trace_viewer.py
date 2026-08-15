"""Deep Trace Viewer — Modern modal popup for analyzing all execution traces.

Features:
 - Tabbed interface: Overview · LLM · Tools · Flow · Thinking · Events
 - Per-event human-readable formatting (no raw JSON dumps)
 - Export to JSON/Markdown
 - Copy full trace to clipboard
 - Keyboard shortcuts: Esc/q close, e export, c copy
 - Triggered via F2 global OR per-turn "View Trace" button
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING

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


def _fmt_kv(data: dict, max_value: int = 200) -> list[str]:
    """Format dict keys/values as human-readable lines (no JSON blobs)."""
    lines = []
    for k, v in data.items():
        if isinstance(v, list):
            if len(v) == 0:
                lines.append(f"  {k}: (empty)")
            elif len(v) <= 3:
                lines.append(f"  {k}: [{', '.join(str(i)[:80] for i in v)}]")
            else:
                lines.append(f"  {k}: [{len(v)} items] {str(v[0])[:60]}\u2026")
        elif isinstance(v, dict):
            if len(v) == 0:
                lines.append(f"  {k}: {{empty}}")
            else:
                inner = ", ".join(f"{ki}: {str(vi)[:40]}" for ki, vi in list(v.items())[:4])
                lines.append(f"  {k}: {{ {inner} }}")
        elif isinstance(v, str):
            preview = v.replace("\n", " ").strip()
            if len(preview) > max_value:
                preview = preview[:max_value] + "\u2026"
            lines.append(f"  {k}: {preview}")
        elif isinstance(v, bool):
            lines.append(f"  {k}: {'yes' if v else 'no'}")
        else:
            lines.append(f"  {k}: {v}")
    return lines


TYPE_ICONS: dict[str, tuple[str, str]] = {
    "LLM_RAW_REQUEST": ("\U0001f4e4", "request"),
    "LLM_RAW_RESPONSE": ("\U0001f4e5", "response"),
    "LLM_PAYLOAD": ("\U0001f9e0", "llm"),
    "LLM_THINKING": ("\U0001f4ad", "thinking"),
    "TOOL_DISPATCH": ("\U0001f527", "tool"),
    "AGENT_ROUTING": ("\U0001f500", "routing"),
    "FUNCTION_CALL": ("\U0001f4de", "fn-call"),
    "FUNCTION_RETURN": ("\u21a9", "fn-return"),
    "ERROR": ("\u274c", "error"),
    "RETRY": ("\U0001f501", "retry"),
    "PERMISSION_CHECK": ("\U0001f512", "perm"),
    "LOG_EVENT": ("\U0001f4dd", "log"),
    "STATE_CHANGE": ("\U0001f504", "state"),
}

_TV_CSS = """
TraceViewerScreen {
    background: rgba(0,0,0,0.75);
    align: center middle;
}
.tv-box {
    width: 96%;
    height: 94%;
    background: #0d1117;
    border: tall #21262d;
    border-top: tall #388bfd;
    layout: vertical;
}
.tv-header {
    height: 3;
    background: #161b22;
    border-bottom: solid #21262d;
    padding: 0 2;
    align-vertical: middle;
}
.tv-title {
    color: #58a6ff;
    text-style: bold;
    width: 1fr;
    height: 1;
    content-align: left middle;
}
.tv-stats {
    color: #8b949e;
    height: 1;
    content-align: left middle;
    margin-right: 2;
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
.tv-stat-row { height: 5; margin: 1 0; }
.tv-stat-box {
    width: 1fr; height: 5;
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
    """Modern full-screen modal trace viewer with 6 tabs."""

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
        title: str = "Execution Trace",
        turn_label: str = "",
    ) -> None:
        super().__init__()
        self.events = events
        self.viewer_title = title
        self.turn_label = turn_label

    # ── compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        ev = self.events
        llm_ev = [e for e in ev if e.event_type.value in ("LLM_RAW_RESPONSE", "LLM_PAYLOAD")]
        tool_ev = [e for e in ev if e.event_type.value == "TOOL_DISPATCH"]
        think_ev = [
            e
            for e in ev
            if e.event_type.value == "LLM_THINKING"
            or (e.event_type.value == "LLM_RAW_RESPONSE" and e.data.get("thinking"))
        ]
        err_ev = [e for e in ev if e.event_type.value == "ERROR" or e.status == "ERROR"]
        route_ev = [e for e in ev if e.event_type.value == "AGENT_ROUTING"]

        subtitle = self.turn_label or f"{len(ev)} events"

        with Vertical(classes="tv-box"):
            with Horizontal(classes="tv-header"):
                yield Label(
                    f"\u26a1 {self.viewer_title}  [dim]{subtitle}[/dim]",
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
                yield Button("\u2b06 Export", id="btn-tv-export", classes="tv-btn tv-btn-export")
                yield Button("\u2398 Copy", id="btn-tv-copy", classes="tv-btn")
                yield Button("\u2715 Close", id="btn-tv-close", classes="tv-btn tv-btn-close")

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
                em_dash = "\u2014"
                yield Label("Session Timing", classes="tv-section-head")
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
                        f"[bold]{name}[/]  [dim]{_fmt_ms(e.duration_ms)}[/]",
                        markup=True,
                    )

            if err_ev:
                yield Label("Errors", classes="tv-section-head")
                for e in err_ev:
                    msg = e.data.get("error", e.data.get("message", e.action))
                    yield Static(
                        f"  [bold red]\u2717[/] [dim]{e.event_type.value}[/]  {str(msg)[:120]}",
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
                tok_in = usage.get("tokens_in", "?")
                tok_out = usage.get("tokens_out", "?")
                finish = resp.data.get("finish_reason", "")
                tcalls = resp.data.get("tool_calls", [])
                content = resp.data.get("response_content", "")
                is_ok = finish not in ("error", "stop_error")
                ts = _fmt_ts(resp.timestamp)

                with Collapsible(
                    title=f"{'✓' if is_ok else '✗'} {model}  {latency}  {ts}  tok: {tok_in}→{tok_out}",
                    collapsed=False,
                ):
                    if req:
                        msgs = req.data.get("messages", [])
                        tools_n = req.data.get("tools_count", 0)
                        yield Static(
                            f"  [dim]Request:[/] {len(msgs)} messages, {tools_n} tools",
                            markup=True,
                        )
                        for msg in msgs[-3:]:
                            role = msg.get("role", "?")
                            mc = msg.get("content", "")
                            if isinstance(mc, list):
                                mc = " ".join(p.get("text", "") for p in mc if isinstance(p, dict))
                            preview = str(mc).replace("\n", " ")[:200]
                            rc = (
                                "tv-llm"
                                if role == "assistant"
                                else "tv-tool"
                                if role == "tool"
                                else "tv-event-val"
                            )
                            yield Static(f"  [{rc}]{role}[/]  {preview}", markup=True)

                    if tcalls:
                        yield Static(f"  [bold green]Tool calls ({len(tcalls)})[/]", markup=True)
                        for tc in tcalls:
                            tname = tc.get("name", "?")
                            targs = tc.get("args", {})
                            if isinstance(targs, dict):
                                ap = ", ".join(
                                    f"{k}={str(v)[:40]}" for k, v in list(targs.items())[:3]
                                )
                            else:
                                ap = str(targs)[:80]
                            yield Static(
                                f"  [bold cyan]  \u2192 {tname}[/]  [dim]{ap}[/]", markup=True
                            )

                    if content:
                        with Collapsible(title="Response text", collapsed=False):
                            for line in content[:2000].split("\n"):
                                yield Static(f"  {line}", classes="tv-response-block")
                            if len(content) > 2000:
                                yield Static(
                                    f"  [dim]\u2026 {len(content) - 2000} more chars[/]",
                                    markup=True,
                                )

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
                f"  [bold green]{ok_n} ok[/]  [bold red]{fail_n} failed[/]  [dim]/ {len(tool_ev)} total[/]",
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
                    title=f"{'✓' if is_ok else '✗'} [{idx}] {name}  {dur}  {ts}  {risk}",
                    collapsed=(idx > 3),
                ):
                    if isinstance(args, dict) and args:
                        yield Static("  [dim]Arguments:[/]", markup=True)
                        for line in _fmt_kv(args):
                            k, _, v = line.partition(":")
                            yield Static(
                                f"  [tv-event-key]{k.strip()}[/] [dim]\u2192[/] {v.strip()}",
                                markup=True,
                            )
                    elif args:
                        yield Static(f"  [dim]args:[/] {str(args)[:200]}", markup=True)

                    if result:
                        with Collapsible(title="Result", collapsed=False):
                            for line in str(result)[:1500].split("\n"):
                                yield Static(f"  {line}", classes="tv-response-block")
                            if len(str(result)) > 1500:
                                yield Static(
                                    f"  [dim]\u2026 {len(str(result)) - 1500} more chars[/]",
                                    markup=True,
                                )

                    if not is_ok and e.data.get("error"):
                        yield Static(f"  [bold red]Error:[/] {e.data['error'][:200]}", markup=True)

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
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("\u00b7", ""))
                color = COLOR_MAP.get(e.event_type.value, "tv-event-dimval")
                ts = _fmt_ts(e.timestamp)
                dur = _fmt_ms(e.duration_ms)
                gap = _fmt_ms((e.timestamp - prev) * 1000)
                gap_s = f"[dim]+{gap}[/] " if gap else ""
                sicon = "✓" if e.status == "OK" else ("✗" if e.status == "ERROR" else " ")
                prev = e.timestamp

                al = e.action
                if e.event_type.value == "TOOL_DISPATCH":
                    al = e.data.get("tool_name", e.action)
                elif "LLM" in e.event_type.value:
                    al = e.data.get("model", e.action)

                yield Static(
                    f"  [dim]{ts}[/] {gap_s}[{color}]{icon} {e.event_type.value}[/]  "
                    f"[bold]{al[:40]}[/]  [dim]{dur}[/]  {sicon}",
                    classes="tv-timeline-row",
                    markup=True,
                )

    # ── Thinking tab ─────────────────────────────────────────────────────────

    def _tab_thinking(self) -> ComposeResult:
        with VerticalScroll(classes="tv-tab-scroll"):
            blocks: list[tuple[str, str, object]] = []
            for e in self.events:
                if e.event_type.value == "LLM_THINKING":
                    blocks.append((e.data.get("model", ""), e.data.get("thinking", ""), e))
            for e in self.events:
                if e.event_type.value == "LLM_RAW_RESPONSE":
                    t = e.data.get("thinking", "")
                    if t:
                        blocks.append((e.data.get("model", ""), t, e))

            if not blocks:
                yield Static(
                    "  [dim]No thinking / reasoning blocks found.\n"
                    "  These appear when the LLM uses extended thinking mode.[/]",
                    classes="tv-empty",
                    markup=True,
                )
                return

            for idx, (model, thinking, e) in enumerate(blocks, 1):
                ts = _fmt_ts(e.timestamp)
                chars = len(thinking)
                lines = thinking.count("\n") + 1

                with Collapsible(
                    title=f"\U0001f4ad Block {idx}  {model}  {chars:,} chars  {lines} lines  {ts}",
                    collapsed=(idx > 1),
                ):
                    for line in thinking.split("\n")[:200]:
                        yield Static(f"  {line}", classes="tv-thinking-block")
                    if lines > 200:
                        yield Static(f"  [dim]\u2026 {lines - 200} more lines[/]", markup=True)

    # ── Events tab ───────────────────────────────────────────────────────────

    def _tab_events(self) -> ComposeResult:
        """Human-readable event log — no raw JSON."""
        with VerticalScroll(classes="tv-tab-scroll"):
            if not self.events:
                yield Static("  [dim]No events.[/]", classes="tv-empty", markup=True)
                return

            yield Static(f"  [dim]{len(self.events)} events captured[/]", markup=True)

            for idx, e in enumerate(self.events, 1):
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("\u00b7", ""))
                ts = _fmt_ts(e.timestamp)
                dur = _fmt_ms(e.duration_ms)
                is_ok = e.status in ("OK", "")
                scls = "tv-ok" if is_ok else "tv-err"
                sicon = "✓" if is_ok else "✗"

                with Collapsible(
                    title=f"{icon} [{idx}] {e.event_type.value}  {e.source}  {dur}  {ts}  {sicon}",
                    collapsed=True,
                ):
                    yield Static(f"  [dim]source:[/] {e.source}", markup=True)
                    yield Static(f"  [dim]action:[/] {e.action}", markup=True)
                    yield Static(f"  [dim]status:[/] [{scls}]{e.status or 'ok'}[/]", markup=True)
                    if dur:
                        yield Static(f"  [dim]duration:[/] {dur}", markup=True)
                    if e.data:
                        yield Static("  [dim]data:[/]", markup=True)
                        for line in _fmt_kv(e.data, max_value=120):
                            k, _, v = line.partition(":")
                            yield Static(
                                f"  [tv-event-key]{k.strip()}[/] [dim]\u2192[/] {v.strip()}",
                                markup=True,
                            )

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

    # backward compat for tests
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
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("\u00b7", ""))
                md_lines.append(f"### [{i}] {icon} {e.event_type.value} — {_fmt_ts(e.timestamp)}")
                md_lines.append(f"- **Source:** `{e.source}`")
                md_lines.append(f"- **Action:** `{e.action}`")
                md_lines.append(f"- **Status:** {e.status or 'ok'}")
                if e.duration_ms > 0:
                    md_lines.append(f"- **Duration:** {_fmt_ms(e.duration_ms)}")
                if e.data:
                    md_lines.append("")
                    md_lines.append("```")
                    md_lines.extend(_fmt_kv(e.data, max_value=300))
                    md_lines.append("```")
                md_lines.append("")

            with open(md_path, "w") as f:
                f.write("\n".join(md_lines))

            self._show_note(f"Exported \u2192 {json_path}  +  {md_path}", ok=True)
        except Exception as exc:
            self._show_note(f"Export failed: {exc}", ok=False)

    def action_copy_trace(self) -> None:
        """Copy trace summary to clipboard."""
        try:
            lines = [f"SAGO Trace \u2014 {len(self.events)} events  {datetime.now().isoformat()}"]
            for i, e in enumerate(self.events, 1):
                icon, _ = TYPE_ICONS.get(e.event_type.value, ("\u00b7", ""))
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
