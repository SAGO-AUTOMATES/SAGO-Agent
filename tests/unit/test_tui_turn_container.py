"""Tests for TUI turn containerization and widget mounting."""

import pytest

from sago.tui.app import SagoApp


@pytest.mark.anyio
async def test_tui_message_exchange_mounting():
    app = SagoApp()
    async with app.run_test() as pilot:
        # User message
        app._add_user_message("Hello from test")
        await pilot.pause()

        # Tool call
        app._add_tool_call("grep_content", {"pattern": "def "}, "match 1\nmatch 2", success=True)
        await pilot.pause()

        # Assistant response
        app._add_assistant_message("Here is your answer:\n```python\nprint('hello')\n```")
        await pilot.pause()

        # Check messages container has children
        messages_container = app.query_one("#messages")
        assert len(messages_container.children) >= 1
