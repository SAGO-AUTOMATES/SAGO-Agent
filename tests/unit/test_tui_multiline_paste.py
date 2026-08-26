"""Unit tests for multiline keyboard shortcuts, dynamic height, and paste in TUI."""

import asyncio
from unittest.mock import MagicMock

from textual.events import Key

from sago.tui.app import SagoTextAreaInput


class TestTuiMultilineAndPaste:
    """Test SagoTextAreaInput multiline, visible height, and paste support."""

    def test_sago_text_area_input_initial_height(self):
        inp = SagoTextAreaInput()
        assert inp.styles.min_height.value == 3
        assert inp.styles.max_height.value == 5
        assert inp.styles.height.value == 3

    def test_sago_text_area_value_property_auto_expands(self):
        inp = SagoTextAreaInput()
        inp.value = "hello\nworld\nline 3"
        assert inp.value == "hello\nworld\nline 3"
        assert inp.styles.height.value == 5

        inp.value = "single line"
        assert inp.styles.height.value == 3

    def test_enter_submits_message(self):
        async def _run():
            inp = SagoTextAreaInput()
            inp.load_text("send this prompt")
            inp.post_message = MagicMock()

            key_event = MagicMock(spec=Key)
            key_event.key = "enter"

            await inp._on_key(key_event)

            key_event.prevent_default.assert_called_once()
            key_event.stop.assert_called_once()
            inp.post_message.assert_called_once()
            submitted = inp.post_message.call_args[0][0]
            assert submitted.value == "send this prompt"

        asyncio.run(_run())

    def test_shift_enter_inserts_newline(self):
        async def _run():
            inp = SagoTextAreaInput()
            inp.load_text("first line")
            inp.insert = MagicMock()
            inp.post_message = MagicMock()

            key_event = MagicMock(spec=Key)
            key_event.key = "shift+enter"

            await inp._on_key(key_event)

            key_event.prevent_default.assert_called_once()
            key_event.stop.assert_called_once()
            inp.insert.assert_called_once_with("\n")

        asyncio.run(_run())
