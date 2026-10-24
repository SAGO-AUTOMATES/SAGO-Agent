"""Exhaustive tests for sago/tui/app.py covering actions, event handlers, and navigation."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from sago.tracking.dev_tracer import DevTraceEvent, TraceEventType
from sago.tui.app import SagoApp
from sago.tui.widgets import get_task_manager


@pytest.mark.asyncio
async def test_tui_app_actions_and_scrolling():
    """Test all viewport scrolling and action handlers in SagoApp."""
    app = SagoApp()
    async with app.run_test() as pilot:
        # Scrolling actions
        app.action_scroll_page_up()
        app.action_scroll_page_down()
        app.action_scroll_line_up()
        app.action_scroll_line_down()
        app.action_scroll_home()
        app.action_scroll_end()
        await pilot.pause()

        # Keyboard scrolling events via on_key
        key_mock = MagicMock()
        key_mock.key = "pageup"
        app.on_key(key_mock)

        key_mock.key = "pagedown"
        app.on_key(key_mock)

        key_mock.key = "end"
        app.on_key(key_mock)

        # History up/down via on_key
        key_mock.key = "up"
        app.on_key(key_mock)

        key_mock.key = "down"
        app.on_key(key_mock)

        # Mouse scrolling
        mouse_mock = MagicMock()
        app.on_mouse_scroll_down(mouse_mock)
        app.on_mouse_scroll_up(mouse_mock)
        app.on_click(mouse_mock)

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_app_modals_and_screen_actions():
    """Test modal screen triggers and actions."""
    app = SagoApp()
    async with app.run_test() as pilot:
        # Open diff viewer
        app.action_open_diff_viewer()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Open file explorer
        app.action_open_file_explorer()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Open session manager
        app.action_open_session_manager()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Open model switcher
        app.action_open_model_switcher()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Open trace viewer
        app.action_open_trace_viewer()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Show shortcuts
        app.action_show_shortcuts()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Toggle dashboard
        app.action_toggle_dashboard()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Tasks action
        app.action_show_tasks()
        tm = get_task_manager()
        _ = tm.create_task("python-engineer", "Test task")
        app.action_cancel_task()


@pytest.mark.asyncio
async def test_tui_app_suggestions_and_input_events():
    """Test autocomplete suggestions, selection navigation, and input lifecycle."""
    app = SagoApp()
    async with app.run_test() as pilot:
        # Direct autocomplete trigger
        app._show_cmd_suggestions("/")
        assert len(app.suggestion_items) > 0

        # Move selection
        app._move_sel(1)
        app._move_sel(-1)
        app._update_highlight()

        # Select current
        app._select_current()

        # Hide suggestions
        app._hide_suggestions()
        assert app.show_suggestions is False

        # File suggestions
        app._show_file_suggestions("pyproject")
        app._show_file_suggestions("~", home=True)

        # Agent suggestions
        app._show_agent_suggestions("py")

        # Model suggestions
        app._show_model_suggestions("gemini")

        # Shortcuts suggestions
        app._show_shortcuts_suggestions("Ctrl")

        # Button events
        app.on_clear_button_clicked()
        app.on_cancel_button_clicked()

        # Reactive watchers
        app.current_effort = "low"
        app.current_agent = "code-reviewer"
        app.yolo_mode = True
        app.current_provider = "deepseek"
        app.current_model = "deepseek-chat"
        await pilot.pause()

        # Trace button event
        mock_btn = MagicMock()
        mock_btn._trace_events = [
            DevTraceEvent(
                timestamp=time.time(),
                event_type=TraceEventType.TOOL_DISPATCH,
                source="test",
                action="test_action",
                data={"tool": "test", "params": {}},
            )
        ]
        mock_btn._trace_label = "Test Trace"
        event = MagicMock(button=mock_btn)
        app.on_view_trace_button(event)
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        # Exception handler
        from rich.errors import MissingStyle

        app.on_exception(MissingStyle("style test"))
        app.on_exception(ValueError("sample error"))
        app.handle_exception(RuntimeError("runtime issue"))


@pytest.mark.asyncio
async def test_tui_app_file_context_and_exit_summary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sample_file = tmp_path / "hello.py"
    sample_file.write_text("print('hello world!')\n")

    app = SagoApp()
    # Test _extract_file_context
    ctx = app._extract_file_context(f"Look at #{sample_file.name} and #{sample_file}")
    assert "hello world!" in ctx

    # Test print_exit_summary with messages
    app.current_session_id = "test-session-123"
    app.messages = [
        {"role": "user", "content": "What is 2+2?"},
        {
            "role": "assistant",
            "content": "4",
            "provider": "google",
            "model": "gemini-2.5-flash",
        },
    ]
    app.session_tokens = {"prompt": 120, "completion": 80, "cost": 0.00015}
    app.session_tool_calls = [
        {"tool": "read_file", "success": True, "duration": 0.04},
        {"tool": "bash", "success": False, "duration": 0.12},
    ]
    app.print_exit_summary()

    # Test print_exit_summary with 0 user queries (auto-clean session branch)
    app2 = SagoApp()
    app2.current_session_id = "ghost-session-456"
    app2.messages = []
    app2.print_exit_summary()


@pytest.mark.asyncio
async def test_tui_app_actions_and_watchers_deep():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Actions
        app.action_toggle_dashboard()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        app.action_show_shortcuts()
        await pilot.pause()
        if len(app.screen_stack) > 1:
            app.pop_screen()
            await pilot.pause()

        app.action_show_tasks()
        app.action_cancel_task()
        app.action_scroll_page_up()
        app.action_scroll_page_down()
        app.action_scroll_line_up()
        app.action_scroll_line_down()
        app.action_scroll_home()
        app.action_scroll_end()
        app.action_dismiss_suggestions()
        app.action_clear_chat()

        # Approval actions
        app.approval_message = "Delete all files?"
        app.action_approve_action()
        app.approval_message = "Delete all files?"
        app.action_deny_action()
        app.on_approve_pressed(MagicMock())
        app.on_deny_pressed(MagicMock())

        # Watchers & helpers
        app.watch_developer_mode(True)
        app.watch_developer_mode(False)
        app.watch_show_action_bar(True)
        app.watch_show_action_bar(False)
        app.watch_current_model("gpt-4o")
        app.watch_current_provider("openai")
        app.watch_current_effort("high")
        app.watch_current_agent("code-reviewer")
        app.watch_yolo_mode(True)
        app.watch_yolo_mode(False)
        app.watch_show_summary(True)

        # Control message checks
        assert app._is_control_message("y") is True
        assert app._is_control_message("yes") is True
        assert app._is_control_message("n") is True
        assert app._is_control_message("no") is True
        assert app._is_control_message("/cancel") is True
        assert app._is_control_message("/help") is True
        assert app._is_control_message("can you help me with python code?") is False

        # Suggestions & selection
        app._show_cmd_suggestions("/effort")
        app._move_sel(1)
        app._select_current()
        app._show_cmd_suggestions("/delegate")
        app._show_cmd_suggestions("/chain")
        app._show_cmd_suggestions("/chain python-engineer,")
        app._show_cmd_suggestions("/agent")

        # History navigation
        app._add_to_history("cmd 1")
        app._add_to_history("cmd 2")
        app._navigate_history("up")
        app._navigate_history("down")

        # Queue processing
        app.is_thinking = False
        app._pending_message_queue.append("/help")
        app._pending_message_queue.append("@python-engineer test")
        app._pending_message_queue.append("regular prompt")
        app._try_process_queue()
        app.watch_is_thinking(False)

        # Direct UI helper calls
        app._show_new_messages_badge()
        app._hide_new_messages_badge()
        app._smart_scroll_end()
        app._show_spinner("Working")
        app._advance_spinner()
        app._update_spinner("Still working")
        app._hide_spinner()
        app._show_approval_bar("Confirm?")
        app._hide_approval_bar()
        app._auto_refresh_models()
        app._resolve_api_model()
        app._get_provider_api_key()
        app._get_provider_key_name()
        app._update_execution_mode("api")
        app._update_execution_mode("native")
        app._periodic_dashboard_update()

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_app_compaction_and_input_submission():
    app = SagoApp()
    async with app.run_test() as pilot:
        from textual.widgets import Static

        msg_box = app.query_one("#messages")
        for i in range(app.TUI_MAX_RENDERED_CARDS + 5):
            msg_box.mount(Static(f"Turn {i}", classes="exchange-box"))
        app._maybe_compact_tui_messages()

        btn = MagicMock(_code_content="print('copied code')")
        event = MagicMock(button=btn)
        app.on_copy_code_button(event)

        btn_err = MagicMock(_code_content="error code")
        event_err = MagicMock(button=btn_err)
        with patch("sago.tools.session.clipboard.ClipboardTool._write_clipboard") as mock_wb:
            mock_wb.return_value = "Error: clipboard failed"
            app.on_copy_code_button(event_err)

        inp_mock = MagicMock()
        # Empty input
        app.on_input_submitted(MagicMock(value="", input=inp_mock))

        # Suggestions direct execute
        app.show_suggestions = True
        app.suggestion_values = ["/dev on"]
        app.suggestion_index = 0
        app.on_input_submitted(MagicMock(value="/dev", input=inp_mock))

        # Suggestions requires more args
        app.show_suggestions = True
        app.suggestion_values = ["/delegate"]
        app.suggestion_index = 0
        app.on_input_submitted(MagicMock(value="/del", input=inp_mock))

        # Suggestions mention
        app.show_suggestions = True
        app.suggestion_values = ["@python-engineer"]
        app.suggestion_index = 0
        app.on_input_submitted(MagicMock(value="@py", input=inp_mock))

        # Queuing while thinking
        app.is_thinking = True
        app.on_input_submitted(MagicMock(value="run my query", input=inp_mock))
        app.is_thinking = False

        # Input shortcuts / approval / deny / cancel
        app.on_input_submitted(MagicMock(value="?", input=inp_mock))

        app.approval_message = "confirm?"
        app.on_input_submitted(MagicMock(value="y", input=inp_mock))

        app.approval_message = "confirm?"
        app.on_input_submitted(MagicMock(value="n", input=inp_mock))

        app.on_input_submitted(MagicMock(value="/cancel", input=inp_mock))

        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_app_extra_coverage_and_buttons():
    """Exercise remaining action buttons, scrolling, MultilineInput, and shell escape in SagoApp."""
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # SagoTextAreaInput key actions while on default screen
        from sago.tui.app import SagoTextAreaInput

        inp = app.query_one(SagoTextAreaInput)
        key_ev = MagicMock(key="shift+enter")
        await inp._on_key(key_ev)
        assert "\n" in inp.text

        key_enter = MagicMock(key="enter")
        await inp._on_key(key_enter)

        # Test shell escape
        app._execute_shell_escape("echo 'hello from test'")
        await pilot.pause(0.2)

        # Trace viewer button handler
        btn_trace = MagicMock(_trace_events=None, _trace_label="turn-1")
        ev_trace = MagicMock(button=btn_trace)
        app.on_view_trace_button(ev_trace)

        mock_event = MagicMock()
        mock_event.event_type.value = "LLM_RAW_RESPONSE"
        mock_event.name = "llm_trace"
        mock_event.timestamp = 1.0
        mock_event.data = {}
        mock_event.agent = "sago"
        btn_trace_with_events = MagicMock(_trace_events=[mock_event], _trace_label="turn-2")
        ev_trace2 = MagicMock(button=btn_trace_with_events)
        with patch.object(app, "push_screen"):
            app.on_view_trace_button(ev_trace2)

        # Scrolling actions
        app.action_scroll_page_up()
        app.action_scroll_page_down()
        app.action_scroll_line_up()
        app.action_scroll_line_down()
        app.action_scroll_home()
        app.action_scroll_end()

        # Global exception handler
        app.on_exception(RuntimeError("Sample test error"))
        from rich.errors import MarkupError

        app.on_exception(MarkupError("Invalid tag"))

        # Action bar buttons with mocked push_screen so stack stays clean
        with patch.object(app, "push_screen"):
            app.on_diff_button_clicked()
            app.on_files_button_clicked()
            app.on_sessions_button_clicked()
            app.on_model_button_clicked()
            app.on_dashboard_button_clicked()
            app.on_help_button_clicked()

        await pilot.pause()
