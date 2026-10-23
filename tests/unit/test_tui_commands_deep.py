"""Deep test suite for sago.tui.commands covering slash command handlers via _handle_command."""

from __future__ import annotations

import pytest

from sago.tui.app import SagoApp
from sago.tui.models import COMMANDS


class TestTuiCommandsDeep:
    """Exercise command handlers on SagoApp to boost statement and branch coverage."""

    def test_commands_dict_integrity(self) -> None:
        """Verify that core slash commands exist in COMMANDS dictionary."""
        expected_commands = [
            "/help",
            "/clear",
            "/model",
            "/provider",
            "/effort",
            "/cost",
            "/dev",
            "/history",
            "/export",
            "/sessions",
            "/delegate",
            "/chain",
            "/orchestrate",
            "/plan",
            "/parallel",
            "/tasks",
            "/tools",
            "/skills",
            "/mcp",
            "/plugins",
            "/graph",
            "/verify",
            "/git",
            "/diff",
            "/undo",
            "/checkpoint",
            "/search",
        ]
        for cmd in expected_commands:
            assert cmd in COMMANDS, f"Command '{cmd}' missing from COMMANDS registry"

    @pytest.mark.asyncio
    async def test_cmd_help_and_status(self) -> None:
        app = SagoApp()
        async with app.run_test() as pilot:
            app._handle_command("/help")
            app._handle_command("/status")
            await pilot.pause()
            container = app.query_one("#messages")
            assert len(container.children) >= 1

    @pytest.mark.asyncio
    async def test_cmd_model_and_provider_switching(self) -> None:
        app = SagoApp()
        async with app.run_test() as _:
            app._handle_command("/model gemini/gemini-2.5-flash")
            assert "gemini" in app.current_model
            app._handle_command("/provider gemini")
            assert app.current_provider in ("gemini", "google")

    @pytest.mark.asyncio
    async def test_cmd_effort_and_cost(self) -> None:
        app = SagoApp()
        async with app.run_test() as pilot:
            app._handle_command("/effort high")
            assert app.current_effort == "high"
            app._handle_command("/cost")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_cmd_theme_and_dev(self) -> None:
        app = SagoApp()
        async with app.run_test() as _:
            app._handle_command("/theme nord")
            assert app.sago_theme == "nord"
            app._handle_command("/dev on")
            assert app.developer_mode is True
            app._handle_command("/dev off")
            assert app.developer_mode is False

    @pytest.mark.asyncio
    async def test_cmd_tools_and_skills_and_mcp(self) -> None:
        app = SagoApp()
        async with app.run_test() as pilot:
            app._handle_command("/tools")
            app._handle_command("/skills")
            app._handle_command("/mcp")
            app._handle_command("/plugins")
            await pilot.pause()
            container = app.query_one("#messages")
            assert len(container.children) >= 3
