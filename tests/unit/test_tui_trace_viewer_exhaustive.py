"""Exhaustive tests for Deep Trace & Dev Console TraceViewerScreen."""

from __future__ import annotations

import time

import pytest
from textual.app import App

from sago.tracking.dev_tracer import DevTraceEvent, TraceEventType
from sago.tui.trace_viewer import (
    TraceViewerScreen,
    _fmt_kv,
    _fmt_ms,
    _fmt_ts,
)


class TraceTestApp(App):
    """Test harness app for TraceViewerScreen."""

    def __init__(self, screen_to_push: TraceViewerScreen) -> None:
        super().__init__()
        self.sago_theme = "nord"
        self._screen_to_push = screen_to_push

    def on_mount(self) -> None:
        self.push_screen(self._screen_to_push)


def test_format_helpers() -> None:
    assert _fmt_ms(0) == ""
    assert _fmt_ms(-5) == ""
    assert _fmt_ms(250) == "250ms"
    assert _fmt_ms(1500) == "1.50s"

    ts = time.time()
    formatted = _fmt_ts(ts)
    assert ":" in formatted and "." in formatted

    data = {
        "empty_list": [],
        "short_list": ["a", "b"],
        "long_list": ["item1", "item2", "item3", "item4", "item5"],
        "empty_dict": {},
        "filled_dict": {"k1": "v1", "k2": "v2"},
        "long_str": "x" * 500,
        "is_true": True,
        "is_false": False,
        "number": 42,
    }
    lines = _fmt_kv(data, max_value=50)
    assert any("empty_list: (empty)" in line for line in lines)
    assert any("short_list: [a, b]" in line for line in lines)
    assert any("5 items" in line for line in lines)
    assert any("empty_dict: {empty}" in line for line in lines)
    assert any("filled_dict: {" in line for line in lines)
    assert any("is_true: yes" in line for line in lines)
    assert any("is_false: no" in line for line in lines)
    assert any("number: 42" in line for line in lines)


@pytest.mark.asyncio
async def test_trace_viewer_empty_events(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    screen = TraceViewerScreen(events=[], title="Empty Trace", turn_label="Turn 0")
    app = TraceTestApp(screen)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen.is_mounted

        # Verify close action
        screen.action_close()
        await pilot.pause()


@pytest.mark.asyncio
async def test_trace_viewer_comprehensive_tabs(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    now = time.time()

    events = [
        DevTraceEvent(
            timestamp=now - 5,
            event_type=TraceEventType.LLM_RAW_REQUEST,
            source="coder",
            action="request",
            data={"messages_count": 3, "model": "gpt-4o"},
            duration_ms=0,
            status="OK",
        ),
        DevTraceEvent(
            timestamp=now - 4.5,
            event_type=TraceEventType.LLM_RAW_RESPONSE,
            source="coder",
            action="response",
            data={
                "model": "gpt-4o",
                "usage": {"tokens_in": 120, "tokens_out": 45},
                "finish_reason": "stop",
                "thinking": "Planning to write the file...",
                "tool_calls": [{"name": "write_file", "args": {"path": "main.py"}}],
                "content": "Here is the code solution.",
            },
            duration_ms=500,
            status="OK",
        ),
        DevTraceEvent(
            timestamp=now - 4,
            event_type=TraceEventType.LLM_THINKING,
            source="coder",
            action="thinking",
            data={"thinking": "Validating output correctness..."},
            duration_ms=100,
            status="OK",
        ),
        DevTraceEvent(
            timestamp=now - 3,
            event_type=TraceEventType.TOOL_DISPATCH,
            source="coder",
            action="execute",
            data={
                "tool_name": "write_file",
                "args": {"path": "main.py", "content": "print('hello')"},
                "result": "File created successfully",
            },
            duration_ms=25,
            status="OK",
        ),
        DevTraceEvent(
            timestamp=now - 2,
            event_type=TraceEventType.AGENT_ROUTING,
            source="orchestrator",
            action="route",
            data={"from_agent": "orchestrator", "to_agent": "coder", "reason": "code writing"},
            duration_ms=10,
            status="OK",
        ),
        DevTraceEvent(
            timestamp=now - 1,
            event_type=TraceEventType.ERROR,
            source="test_runner",
            action="assertion",
            data={"error": "AssertionError: expected 1 got 0"},
            duration_ms=5,
            status="ERROR",
        ),
        DevTraceEvent(
            timestamp=now,
            event_type=TraceEventType.STATE_CHANGE,
            source="session",
            action="state_update",
            data={"status": "completed"},
            duration_ms=0,
            status="OK",
        ),
    ]

    screen = TraceViewerScreen(events=events, title="Full Trace", turn_label="Turn 1")
    app = TraceTestApp(screen)

    async with app.run_test() as pilot:
        await pilot.pause()
        assert screen.is_mounted

        # Switch to each tab
        tabbed_content = screen.query_one("TabbedContent")
        for tab_id in [
            "tab-overview",
            "tab-llm",
            "tab-tools",
            "tab-flow",
            "tab-graph",
            "tab-thinking",
            "tab-events",
        ]:
            tabbed_content.active = tab_id
            await pilot.pause()

        # Trigger export
        screen.action_export_trace()
        await pilot.pause()

        exported_files = list(tmp_path.glob("sago_trace_*.json"))
        assert len(exported_files) >= 1
        exported_md = list(tmp_path.glob("sago_trace_*.md"))
        assert len(exported_md) >= 1

        # Test header stats visibility
        screen._set_header_stats(True)
        screen._set_header_stats(False)

        # Trigger close
        screen._on_close_btn()
        await pilot.pause()
