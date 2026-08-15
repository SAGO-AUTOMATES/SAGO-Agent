"""Unit tests for TUI TraceViewerScreen modal."""

import pytest
from textual.app import App, ComposeResult

from sago.tracking.dev_tracer import DevTraceEvent, TraceEventType
from sago.tui.trace_viewer import TraceViewerScreen


@pytest.mark.asyncio
async def test_trace_viewer_modal_mount():
    """Test mounting TraceViewerScreen with sample events."""
    import time

    now = time.time()
    events = [
        DevTraceEvent(
            timestamp=now,
            event_type=TraceEventType.LLM_RAW_REQUEST,
            source="test_llm",
            action="REQUEST",
            data={"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]},
        ),
        DevTraceEvent(
            timestamp=now + 0.1,
            event_type=TraceEventType.LLM_RAW_RESPONSE,
            source="test_llm",
            action="RESPONSE",
            data={
                "model": "gpt-4o",
                "response_content": "world",
                "thinking": "analyzing...",
                "tool_calls": [{"name": "read_file", "args": {"file_path": "a.txt"}}],
            },
        ),
        DevTraceEvent(
            timestamp=now + 0.2,
            event_type=TraceEventType.TOOL_DISPATCH,
            source="executor",
            action="read_file",
            data={"tool_name": "read_file", "arguments": {"file_path": "a.txt"}},
        ),
    ]

    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield from ()

    app = TestApp()
    async with app.run_test() as pilot:
        screen = TraceViewerScreen(events)
        await app.push_screen(screen)
        await pilot.pause()
        assert len(screen.events) == 3

        # Close button should exist with new id
        btn = screen.query_one("#btn-tv-close")
        assert btn is not None
        screen._on_close_btn()


@pytest.mark.asyncio
async def test_sago_app_f2_and_dev_view(monkeypatch):
    """Test F2 action and /dev view command in SagoApp."""
    from sago.tracking.dev_tracer import get_dev_tracer
    from sago.tui.app import SagoApp

    tracer = get_dev_tracer()
    tracer.clear()
    tracer.record(TraceEventType.TOOL_DISPATCH, "test_source", "test_action", data={"k": "v"})

    app = SagoApp()
    async with app.run_test() as pilot:
        # Test action_open_trace_viewer
        app.action_open_trace_viewer()
        await pilot.pause()
        assert len(app.screen_stack) > 1

        # Close screen
        app.pop_screen()
        await pilot.pause()

        # Test /dev view command
        app._handle_developer_command("view")
        await pilot.pause()
        assert len(app.screen_stack) > 1
        app.pop_screen()
