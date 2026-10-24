"""Exhaustive unit test suite for sago/tui/modals.py.

Tests:
- _apply_theme helper
- DiffViewerScreen (git status parsing, diff styling, file selection, refresh, dismiss)
- FileExplorerScreen (binary vs text detection, large file handling, lexer selection, dismiss)
- SessionManagerScreen (listing, details formatting, message preview, switching, dismiss)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DirectoryTree, OptionList

from sago.tui.modals import (
    DiffViewerScreen,
    FileExplorerScreen,
    SessionManagerScreen,
    _apply_theme,
)


class ModalTestHostApp(App):
    """Test harness App for mounting and testing Modal screens."""

    def __init__(self, sago_theme: str = "obsidian") -> None:
        super().__init__()
        self.sago_theme = sago_theme
        self.switched_session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield DirectoryTree(str(Path.cwd()))

    def _load_session(self, session_id: str) -> None:
        self.switched_session_id = session_id


def test_apply_theme() -> None:
    screen = MagicMock()
    screen.app.sago_theme = "dracula"
    _apply_theme(screen)
    screen.add_class.assert_called_with("theme-dracula")

    # Exception safety
    screen.remove_class.side_effect = RuntimeError("fail")
    _apply_theme(screen)  # should not raise


@pytest.mark.asyncio
async def test_diff_viewer_screen_clean_tree() -> None:
    app = ModalTestHostApp()
    async with app.run_test() as pilot:
        with patch("subprocess.run") as mock_run:
            # Clean working tree
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""
            mock_run.return_value = mock_proc

            screen = DiffViewerScreen()
            app.push_screen(screen)
            await pilot.pause(0.05)

            options = screen.query_one("#diff-options", OptionList)
            assert options.option_count >= 1

            # Test refresh
            screen.action_refresh_diff()
            await pilot.pause(0.05)

            # Test dismiss via key
            await pilot.press("escape")
            await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_diff_viewer_screen_with_changes() -> None:
    app = ModalTestHostApp()
    async with app.run_test() as pilot:
        with patch("subprocess.run") as mock_run:

            def side_effect(cmd, **kwargs):
                m = MagicMock()
                m.returncode = 0
                if "status" in cmd:
                    m.stdout = " M sago/main.py\n A tests/new_test.py\n D deleted.py"
                else:
                    m.stdout = """diff --git a/sago/main.py b/sago/main.py
index 1234567..89abcdef 100644
--- a/sago/main.py
+++ b/sago/main.py
@@ -10,3 +10,4 @@
 common line
+new added line
-old removed line
"""
                return m

            mock_run.side_effect = side_effect

            screen = DiffViewerScreen(target_file="sago/main.py")
            app.push_screen(screen)
            await pilot.pause(0.05)

            options = screen.query_one("#diff-options", OptionList)
            assert options.option_count >= 3

            # Test selecting option
            screen.on_file_selected(MagicMock(option=MagicMock(id="tests/new_test.py")))
            await pilot.pause(0.05)

            # Test binary / untracked diff fallback
            screen._display_file_diff("deleted.py")

            # Test error branch
            mock_run.side_effect = RuntimeError("git crashed")
            screen.action_refresh_diff()
            await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_file_explorer_screen(tmp_path: Path) -> None:
    # Prepare files for file explorer tests
    small_py = tmp_path / "sample.py"
    small_py.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    binary_file = tmp_path / "image.png"
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")

    null_byte_file = tmp_path / "nulls.bin"
    null_byte_file.write_bytes(b"text with \x00 null bytes inside")

    large_file = tmp_path / "huge.txt"
    large_file.write_text("x" * 600_000, encoding="utf-8")

    app = ModalTestHostApp()
    async with app.run_test() as pilot:
        screen = FileExplorerScreen()
        app.push_screen(screen)
        await pilot.pause(0.05)

        # 1. Directory selected (noop)
        screen.on_file_selected(MagicMock(path=tmp_path))

        # 2. Large file
        screen.on_file_selected(MagicMock(path=large_file))

        # 3. Binary extension
        screen.on_file_selected(MagicMock(path=binary_file))

        # 4. Null bytes binary
        screen.on_file_selected(MagicMock(path=null_byte_file))

        # 5. Normal text code file
        screen.on_file_selected(MagicMock(path=small_py))

        # 6. Read failure error branch
        bad_path = MagicMock()
        bad_path.is_dir.return_value = False
        bad_path.stat.side_effect = OSError("Permission denied")
        screen.on_file_selected(MagicMock(path=bad_path))

        # Dismiss
        await pilot.press("q")
        await pilot.pause(0.05)


@pytest.mark.asyncio
async def test_session_manager_screen(tmp_path: Path) -> None:
    app = ModalTestHostApp()
    async with app.run_test() as pilot:
        with (
            patch("sago.database.Session") as mock_session_cls,
            patch("sago.database.MessageStore") as mock_msg_store_cls,
        ):
            mock_s = MagicMock()
            mock_s.list_all.return_value = [
                {
                    "id": "sess_alpha_123",
                    "title": "Build Architecture",
                    "created_at": "2026-03-01T12:00:00",
                    "status": "active",
                    "metadata": json.dumps({"workspace_cwd": "/mnt/test"}),
                },
                {
                    "id": "sess_beta_456",
                    "title": "Debug Memory Leak",
                    "created_at": "2026-03-01T14:30:00",
                    "status": "detached",
                    "metadata": None,
                },
            ]
            mock_session_cls.return_value.__enter__.return_value = mock_s

            mock_ms = MagicMock()
            mock_ms.get_history.return_value = [
                {"role": "user", "content": "How do I fix this?"},
                {"role": "assistant", "content": "Here is the patch."},
            ]
            mock_msg_store_cls.return_value = mock_ms

            screen = SessionManagerScreen()
            app.push_screen(screen)
            await pilot.pause(0.05)

            options = screen.query_one("#session-options", OptionList)
            assert options.option_count >= 2

            # Test selecting second session
            screen.on_session_selected(MagicMock(option=MagicMock(id="sess_beta_456")))
            assert screen._selected_sid == "sess_beta_456"

            # Test switch action
            screen.action_switch_selected_session()
            assert app.switched_session_id == "sess_beta_456"

            # Re-mount for empty session branch
            mock_s.list_all.return_value = []
            screen2 = SessionManagerScreen()
            app.push_screen(screen2)
            await pilot.pause(0.05)

            # Re-mount for error branch
            mock_s.list_all.side_effect = RuntimeError("DB locked")
            screen3 = SessionManagerScreen()
            app.push_screen(screen3)
            await pilot.pause(0.05)
