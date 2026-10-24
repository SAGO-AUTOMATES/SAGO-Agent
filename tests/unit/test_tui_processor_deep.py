"""Deep exhaustive tests for sago/tui/processor.py."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sago.tui.app import SagoApp
from sago.tui.processor import (
    _build_local_summary_markdown,
    _is_summary_intent,
)


def test_is_summary_intent_variants() -> None:
    # Empty
    assert _is_summary_intent("") is False
    assert _is_summary_intent("   ") is False

    # Positive matches
    assert _is_summary_intent("so what was the summary?") is True
    assert _is_summary_intent("summarize what you did") is True
    assert _is_summary_intent("what was done") is True
    assert _is_summary_intent("what did you do") is True
    assert _is_summary_intent("what was the summary of the work") is True
    assert _is_summary_intent("give me a brief summary") is True

    # Typo tolerance
    assert _is_summary_intent("can you provide a sumamry of changes") is True
    assert _is_summary_intent("summry of work done") is True

    # File hints should NOT be treated as session summary (requires tool use)
    assert _is_summary_intent("summarize sago/tui/app.py") is False
    assert _is_summary_intent("summarize this file") is False
    assert _is_summary_intent("summarize README.md") is False
    assert _is_summary_intent("#file summarize the contents") is False

    # But file hint + explicit prior work IS session summary
    assert _is_summary_intent("summarize what you did with README.md") is True


def test_build_local_summary_markdown() -> None:
    messages = [
        {"role": "user", "content": "build authentication"},
        {"role": "assistant", "content": "implemented auth in auth.py"},
    ]
    tool_calls = [
        {"tool": "write_file", "agent": "coder", "args": {"path": "auth.py"}, "success": True},
        {
            "tool": "execute_shell",
            "agent": "tester",
            "args": {"command": "pytest"},
            "success": True,
        },
        {"tool": "read_file", "agent": "coder", "args": {"path": "missing.txt"}, "success": False},
    ]

    summary = _build_local_summary_markdown(
        messages=messages,
        tool_calls=tool_calls,
        traces=[],
        project_analysis="Architecture verified cleanly.",
        total_in=1200,
        total_out=450,
        elapsed=3.5,
    )

    assert "Summary" in summary or "Overview" in summary or "Tools" in summary or "coder" in summary
    assert "auth.py" in summary or "write_file" in summary


@pytest.mark.asyncio
async def test_shell_execution_escape_and_summary_handler() -> None:
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # Set user message so active exchange card is present
        app._add_user_message("Test command")
        await pilot.pause()

        import threading

        async def run_in_thread(target, *args):
            t = threading.Thread(target=target, args=args, daemon=True)
            t.start()
            for _ in range(50):
                if not t.is_alive():
                    break
                await pilot.pause(0.05)

        # 1. Shell execution escape (!echo hello)
        await run_in_thread(app._process_message_thread, "!echo 'hello sago test'")
        await pilot.pause()

        # 2. Summary intent handling
        # Mock get_tui_client for summary call
        mock_summary_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "## Summary of completed work\nCategorized by agent."
        mock_summary_client.chat.completions.create.return_value.choices = [mock_choice]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "sago.llm.tui_providers.get_tui_client",
                lambda prov, model: (mock_summary_client, "gpt-4o"),
            )

            await run_in_thread(
                app._process_message_thread, "so what was the summary of what you did?"
            )
            await pilot.pause()

            # 3. Provider error branch in message processing
            mp.setattr(
                "sago.llm.tui_providers.get_tui_client",
                MagicMock(side_effect=ValueError("Missing API key for custom-provider")),
            )
            app.current_provider = "custom-provider"
            await run_in_thread(app._process_message_thread, "ordinary query without key")
            await pilot.pause()


@pytest.mark.asyncio
async def test_process_message_queue_serialized() -> None:
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()

        # When app.is_thinking is True, new messages are added to _pending_message_queue
        app.is_thinking = True
        app._pending_message_queue.append("first queued message")
        app._pending_message_queue.append("second queued message")

        assert len(app._pending_message_queue) == 2
        assert "first queued message" in app._pending_message_queue

        # While thinking, _try_process_queue keeps them queued
        app._try_process_queue()
        assert len(app._pending_message_queue) == 2

        # When thinking completes, next message is processed
        app.is_thinking = False
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(app, "_process_message", MagicMock())
            app._try_process_queue()
            assert len(app._pending_message_queue) == 1
            assert app._pending_message_queue[0] == "second queued message"
