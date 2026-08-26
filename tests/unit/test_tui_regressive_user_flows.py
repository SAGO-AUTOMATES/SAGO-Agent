"""Comprehensive regression test suite for all user interaction flows in Sago TUI."""

import asyncio

from sago.tui.app import SagoApp, SagoTextAreaInput


class TestTuiRegressiveUserFlows:
    """Comprehensive regression tests covering all user interaction scenarios."""

    def test_user_flow_typing_and_submitting(self):
        """User types message, hits enter, verifies message submission and clearing."""

        async def _run():
            app = SagoApp()
            async with app.run_test() as pilot:
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                assert inp.styles.height.value == 3

                # Type input
                await pilot.press("h", "e", "l", "l", "o")
                assert inp.value == "hello"

                # Hit Enter to submit
                await pilot.press("enter")
                # After submit, value is cleared and reset to height 3
                assert inp.value == ""
                assert inp.styles.height.value == 3

        asyncio.run(_run())

    def test_user_flow_multiline_typing(self):
        """User enters multiline prompt using shift+enter, expands up to max height."""

        async def _run():
            app = SagoApp()
            async with app.run_test() as pilot:
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                await pilot.press("l", "i", "n", "e", "1")
                await pilot.press("shift+enter")
                await pilot.press("l", "i", "n", "e", "2")
                await pilot.press("shift+enter")
                await pilot.press("l", "i", "n", "e", "3")

                assert inp.value == "line1\nline2\nline3"
                assert inp.styles.height.value >= 4

        asyncio.run(_run())

    def test_user_flow_slash_command_autocomplete_tab(self):
        """User types /con and hits Tab to autocomplete /continue."""

        async def _run():
            app = SagoApp()
            async with app.run_test() as pilot:
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                inp.value = "/con"
                app._show_cmd_suggestions("/con")
                assert app.show_suggestions is True
                assert len(app.suggestion_values) > 0

                # Hit Tab
                await pilot.press("tab")
                assert app.show_suggestions is False
                assert inp.value.startswith("/continue ")

        asyncio.run(_run())

    def test_user_flow_agent_mention_autocomplete(self):
        """User types @py and autocompletes @python-engineer."""

        async def _run():
            app = SagoApp()
            async with app.run_test():
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                inp.value = "@py"
                app._show_agent_suggestions("py")
                assert app.show_suggestions is True

                # Select current via Tab
                app._select_current()
                assert inp.value.startswith("@python-")

        asyncio.run(_run())

    def test_user_flow_file_mention_autocomplete(self):
        """User types #ca and autocompletes file path."""

        async def _run():
            app = SagoApp()
            async with app.run_test():
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                inp.value = "#calc"
                app._show_file_suggestions("calc")
                # If suggestions found, Tab completes it
                if app.suggestion_values:
                    app._select_current()
                    assert "#" in inp.value

        asyncio.run(_run())

    def test_user_flow_command_history_up_down(self):
        """User uses Up and Down arrows to recall previous commands."""

        async def _run():
            app = SagoApp()
            async with app.run_test():
                inp = app.query_one("#msg-input", SagoTextAreaInput)
                app._add_to_history("first command")
                app._add_to_history("second command")

                # Up arrow recalls second command
                app._navigate_history("up")
                assert inp.value == "second command"

                # Up arrow again recalls first command
                app._navigate_history("up")
                assert inp.value == "first command"

                # Down arrow goes back to second command
                app._navigate_history("down")
                assert inp.value == "second command"

        asyncio.run(_run())

    def test_user_flow_question_mark_shortcuts(self):
        """User types ? to see quick shortcuts."""

        async def _run():
            app = SagoApp()
            async with app.run_test():
                app._show_shortcuts_suggestions("?")
                assert app.show_suggestions is True
                assert any("F1" in item for item in app.suggestion_items)

        asyncio.run(_run())

    def test_user_flow_pageup_pagedown_scrolling(self):
        """User presses PageUp / PageDown to scroll messages pane."""

        async def _run():
            app = SagoApp()
            async with app.run_test() as pilot:
                # Should not throw any exception
                await pilot.press("pageup")
                await pilot.press("pagedown")
                await pilot.press("end")

        asyncio.run(_run())
