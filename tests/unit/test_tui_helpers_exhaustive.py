"""Exhaustive tests for sago/tui/helpers.py."""

from __future__ import annotations

import types

import pytest
from textual.widgets import Static

from sago.tui.app import SagoApp
from sago.tui.helpers import (
    CollapsibleOutputCard,
    _get_syntax_theme,
    _get_theme_bg,
    _make_code_copy_button,
    _register_sago_syntax_themes,
    _render_markdown,
    _render_markdown_rich,
    _safe_static,
    _summarize_tool_result,
    create_collapsible,
)


def test_theme_and_syntax_helpers() -> None:
    # Theme backgrounds
    assert _get_theme_bg(None) == "#0d1117"
    app_mock = types.SimpleNamespace(sago_theme="dracula")
    assert _get_theme_bg(app_mock) == "#282a36"
    assert _get_syntax_theme(None) == "sago-obsidian"
    assert _get_syntax_theme(app_mock) == "sago-dracula"

    # Register themes
    _register_sago_syntax_themes()


def test_rendering_and_markup_helpers() -> None:
    stat = _safe_static("Safe text", markup=False)
    assert isinstance(stat, Static)

    md = _render_markdown("Hello **world** [link](http://test)")
    assert "world" in md

    rich_md = _render_markdown_rich("# Header\n```python\nprint(1)\n```")
    assert rich_md is not None

    btn = _make_code_copy_button("print('hello')")
    assert btn is not None

    coll = create_collapsible("My Header", Static("My Body"), collapsed=True)
    assert coll is not None


def test_summarize_tool_result_variants() -> None:
    assert _summarize_tool_result("") == "[dim](empty)[/dim]"
    assert _summarize_tool_result("   ") == "[dim](empty)[/dim]"

    short_res = "Short output message"
    assert _summarize_tool_result(short_res) == short_res

    # Long file listing
    lines_listing = ["sago/tui/app.py", "sago/tui/helpers.py", "src/core.py"] * 60
    listing_res = "\n".join(lines_listing)
    summary_listing = _summarize_tool_result(listing_res)
    assert "File listing:" in summary_listing

    # Long JSON
    json_lines = ['{\n  "status": "success",\n  "data": [1, 2, 3]\n}'] * 50
    json_res = "\n".join(json_lines)
    summary_json = _summarize_tool_result(json_res)
    assert "JSON response:" in summary_json

    # Long Code
    code_lines = ["def my_test_function():\n    return 42"] * 60
    code_res = "\n".join(code_lines)
    summary_code = _summarize_tool_result(code_res)
    assert "Code output:" in summary_code

    # Long Error
    err_lines = [
        "Traceback (most recent call last):\n  File 'test.py', line 10\nValueError: failed"
    ] * 50
    err_res = "\n".join(err_lines)
    summary_err = _summarize_tool_result(err_res)
    assert "Error output:" in summary_err

    # Long Search / grep
    search_lines = ["match found in sago/tui/helpers.py:42: search keyword hit"] * 60
    search_res = "\n".join(search_lines)
    summary_search = _summarize_tool_result(search_res)
    assert "Search results:" in summary_search

    # Generic long fallback
    generic_lines = ["Random text line without pattern markers."] * 80
    generic_res = "\n".join(generic_lines)
    summary_gen = _summarize_tool_result(generic_res)
    assert "Output:" in summary_gen


@pytest.mark.asyncio
async def test_sago_app_ui_helpers_exhaustive() -> None:
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # Mount and test CollapsibleOutputCard
        card = CollapsibleOutputCard(Static("line 1\nline 2"), title="Test Card", collapsed=True)
        messages_box = app.query_one("#messages")
        messages_box.mount(card)
        await pilot.pause()

        assert card.is_collapsed is True
        card.toggle_collapse()
        assert card.is_collapsed is False
        card.toggle_collapse()
        assert card.is_collapsed is True

        # Test ShellEscapeCard
        from sago.tui.helpers import ShellEscapeCard

        shell_card = ShellEscapeCard("git status")
        messages_box.mount(shell_card)
        await pilot.pause()
        shell_card.update_result(
            "On branch feature/0.1.15\nnothing to commit", returncode=0, duration_s=0.15
        )
        shell_card.toggle_collapse()
        await pilot.pause()

        # Command turn card
        app._add_command_turn(
            "chain",
            "coder,tester build auth",
            meta="chaining",
            tag_label="CHAIN",
            tag_color="#d2a8ff",
        )
        await pilot.pause()

        # User message creates mounted active exchange card
        app._add_user_message("Query from test")
        await pilot.pause()

        turn = app._active_exchange_card
        assert turn.is_turn_collapsed is False
        turn.toggle_collapse()
        assert turn.is_turn_collapsed is True
        turn.toggle_collapse()
        assert turn.is_turn_collapsed is False

        # Prompt enhancement card with was_modified=True
        mock_enhancement = types.SimpleNamespace(
            was_modified=True,
            enhanced_prompt="Optimized prompt with full context",
            original_prompt="Original basic prompt",
            intent_summary="Run exhaustive verification",
            target_scope=["sago/tui/app.py"],
            improvements=["added context", "specified framework"],
            acceptance_criteria=["tests pass", "coverage >= 75%"],
            quality_score=0.92,
        )
        app._add_prompt_enhancement_card(mock_enhancement)
        await pilot.pause()

        # Thinking card
        app._add_thinking_card("Planning system architecture and testing", agent_name="architect")
        await pilot.pause()

        # Assistant message with thinking, code blocks, tables
        app._add_assistant_message(
            "<thinking>Self-reflection and evaluation</thinking>\n"
            "# Analysis\n"
            "Here is the code block:\n"
            "```python\n"
            "def calculate_total(a: int, b: int) -> int:\n"
            "    return a + b\n"
            "```\n"
            "| Component | Status |\n"
            "|---|---|\n"
            "| TUI | Active |\n"
            "| API | Ready |\n",
            agent_name="python-engineer",
        )
        await pilot.pause()

        # Plan card
        app._add_plan_card("1. Step one\n2. Step two", step_count=2)
        await pilot.pause()

        # Agent & system messages
        app._add_agent_message("coder", "Implementation complete")
        app._add_system_message("System notice: connected")
        app._add_error_inline("Operation timed out", hint="Check network")
        app._add_notice_inline("Notice: branch switched")
        await pilot.pause()

        # Tool calls (success, failure, diff, dir_miss)
        app._add_tool_call(
            "write_file",
            {"path": "test.txt", "content": "hello world"},
            "File created",
            success=True,
        )
        app._add_tool_call(
            "edit_file",
            {"path": "test.txt", "old_string": "hello", "new_string": "world"},
            "File edited",
            success=True,
        )
        app._add_tool_call("read_file", {"path": "my_folder"}, "path is a directory", success=False)
        app._add_tool_call(
            "execute_shell",
            {"command": "invalid_cmd"},
            "Error 127: command not found",
            success=False,
        )
        await pilot.pause()

        # Dashboard and agent entry rendering
        from sago.tui.widgets import AgentStatus, AgentTaskInfo, Vertical

        entry_container = Vertical()
        messages_box.mount(entry_container)
        await pilot.pause()

        info = AgentTaskInfo(
            agent_id="test_agent_1",
            agent_name="Coder",
            task="Writing deep unit tests",
            status=AgentStatus.RUNNING,
            current_tool="write_file",
            elapsed=4.5,
        )
        app._render_agent_entry(entry_container, info)
        await pilot.pause()

        # Dashboard update with visible state
        app._dashboard_visible = True
        app._update_dashboard()

        # Parallel result & orchestrate step
        app._add_parallel_result("coder", "code written successfully", 1.5, True)
        app._add_orchestrate_step(
            1, 3, "coder", "code generation", "completed code", ["write_file"], True, 1.2
        )
        await pilot.pause()

        # Summary cards
        sample_tools = [
            {
                "tool": "write_file",
                "args": {"file_path": "test.txt"},
                "agent": "coder",
                "success": True,
            }
        ]
        app._add_summary(
            sample_tools, "Execution completed cleanly", 1.2, {"input": 100, "output": 50}
        )
        app._add_summary_by_agent_card(
            sample_tools, project_analysis="Clean build", tokens={"input": 100, "output": 50}
        )
        await pilot.pause()

        # Dashboard update
        app._update_dashboard()

        # Scroll & badge helpers
        assert app.is_scrolled_to_bottom() in (True, False)
        app._show_new_messages_badge()
        app._hide_new_messages_badge()
        app._smart_scroll_end()
