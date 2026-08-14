"""Tests for TUI turn containerization, thinking step containment, and theme switching."""

import pytest

from sago.tui.app import SagoApp
from sago.tui.helpers import ExchangeTurnCard


@pytest.mark.anyio
async def test_tui_message_exchange_mounting():
    app = SagoApp()
    async with app.run_test() as pilot:
        # User message
        app._add_user_message("Hello from test")
        await pilot.pause()

        # Plan card
        app._add_plan_card("1. [x] Analyze codebase\n2. [ ] Write tests", step_count=2)
        await pilot.pause()

        # Tool call
        app._add_tool_call("grep_content", {"pattern": "def "}, "match 1\nmatch 2", success=True)
        await pilot.pause()

        # Assistant response with thinking block
        app._add_assistant_message(
            "<thinking>Detailed architectural analysis of authentication</thinking>\nHere is your answer:\n```python\nprint('hello')\n```"
        )
        await pilot.pause()

        # Check messages container has ExchangeTurnCard
        messages_container = app.query_one("#messages")
        assert len(messages_container.children) >= 1
        turn = messages_container.query_one(ExchangeTurnCard)
        assert turn is not None
        assert "Hello from test" in turn.prompt


@pytest.mark.anyio
async def test_tui_theme_switching():
    app = SagoApp()
    async with app.run_test() as pilot:
        # Test theme command
        app._set_theme("nord")
        await pilot.pause()
        assert app.sago_theme == "nord"

        app._set_theme("dracula")
        await pilot.pause()
        assert app.sago_theme == "dracula"

        app._set_theme("monokai")
        await pilot.pause()
        assert app.sago_theme == "monokai"

        app._set_theme("obsidian")
        await pilot.pause()
        assert app.sago_theme == "obsidian"


@pytest.mark.anyio
async def test_tui_collapse_command():
    app = SagoApp()
    async with app.run_test() as pilot:
        app._add_user_message("First query")
        app._add_assistant_message("First response")
        await pilot.pause()

        app._add_user_message("Second query")
        app._add_assistant_message("Second response")
        await pilot.pause()

        # Collapse all
        app._collapse_chats()
        await pilot.pause()

        turn_cards = list(app.query_one("#messages").query(ExchangeTurnCard))
        assert len(turn_cards) == 2
        for c in turn_cards:
            assert c.is_turn_collapsed is True

        # Expand all
        app._collapse_chats("expand")
        await pilot.pause()
        for c in turn_cards:
            assert c.is_turn_collapsed is False
