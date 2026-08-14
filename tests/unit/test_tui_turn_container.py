"""Tests for TUI turn containerization, thinking step containment, theme switching, developer mode, and autocompletion."""

import pytest

from sago.tui.app import SagoApp
from sago.tui.helpers import ExchangeTurnCard
from sago.tui.models import THEMES


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
        for theme_name in THEMES:
            app._set_theme(theme_name)
            await pilot.pause()
            assert app.sago_theme == theme_name


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


@pytest.mark.anyio
async def test_tui_developer_mode():
    app = SagoApp()
    async with app.run_test() as pilot:
        assert app.developer_mode is False

        # Turn ON
        app._handle_developer_command("on")
        await pilot.pause()
        assert app.developer_mode is True

        # Check logs / traces / export subcommands
        app._handle_developer_command("logs")
        app._handle_developer_command("traces")
        app._handle_developer_command("export")
        await pilot.pause()

        # Turn OFF
        app._handle_developer_command("off")
        await pilot.pause()
        assert app.developer_mode is False


@pytest.mark.anyio
async def test_tui_smart_suggestions():
    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # /model suggestion
        app._show_cmd_suggestions("/model gpt")
        assert app.show_suggestions is True
        assert any("gpt" in v.lower() for v in app.suggestion_values)

        # /theme suggestion
        app._show_cmd_suggestions("/theme drac")
        assert any("dracula" in v.lower() for v in app.suggestion_values)

        # /dev suggestion
        app._show_cmd_suggestions("/dev ")
        assert any("on" in v.lower() for v in app.suggestion_values)


@pytest.mark.anyio
async def test_tui_checkpoint_command():
    app = SagoApp()
    async with app.run_test() as pilot:
        app._handle_checkpoint_command("list")
        await pilot.pause()
        app._handle_checkpoint_command("create Unit Test Snapshot")
        await pilot.pause()


@pytest.mark.anyio
async def test_tui_shortcuts_modal():
    from sago.tui.screens.shortcuts import ShortcutsScreen

    app = SagoApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Test shortcuts screen composition
        screen = ShortcutsScreen()
        app.push_screen(screen)
        await pilot.pause()
        assert len(app.screen_stack) >= 2
        screen.dismiss()
        await pilot.pause()

        # Test trigger via command
        app._handle_shortcuts_command()
        await pilot.pause()

        # Test ? trigger suggestion
        app._show_shortcuts_suggestions("?")
        assert app.show_suggestions is True
        assert any("?" in v for v in app.suggestion_values)


@pytest.mark.anyio
async def test_tui_turn_header_collapse():
    app = SagoApp()
    async with app.run_test() as pilot:
        app._add_user_message("Test message for collapse")
        app._add_assistant_message("Test assistant reply")
        await pilot.pause()

        card = app.query_one(ExchangeTurnCard)
        assert card is not None
        assert card.is_turn_collapsed is False

        # Verify bottom collapse button has been removed for a clean UI
        assert len(card.query(".btn-collapse-turn")) == 0

        # Click / toggle collapse
        card.toggle_collapse()
        await pilot.pause()
        assert card.is_turn_collapsed is True

        # Click / toggle again to expand
        card.toggle_collapse()
        await pilot.pause()
        assert card.is_turn_collapsed is False
