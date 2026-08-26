"""Unit tests for sago tui -w / -p / --workspace / --path CLI options."""

import os
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from sago.main import cli


class TestTuiWorkspaceOption:
    """Test workspace directory configuration via CLI options."""

    def test_tui_workspace_short_flag(self, tmp_path):
        runner = CliRunner()
        target_dir = tmp_path / "custom_workspace_w"

        with patch("sago.tui.app.SagoApp.run") as mock_app_run:
            result = runner.invoke(cli, ["tui", "-w", str(target_dir)])
            assert result.exit_code == 0
            assert target_dir.exists()
            assert Path(os.getcwd()).resolve() == target_dir.resolve()
            mock_app_run.assert_called_once()

    def test_tui_path_flag(self, tmp_path):
        runner = CliRunner()
        target_dir = tmp_path / "custom_workspace_path"

        with patch("sago.tui.app.SagoApp.run") as mock_app_run:
            result = runner.invoke(cli, ["tui", "--path", str(target_dir)])
            assert result.exit_code == 0
            assert target_dir.exists()
            assert Path(os.getcwd()).resolve() == target_dir.resolve()
            mock_app_run.assert_called_once()

    def test_tui_auto_creates_nonexistent_workspace(self, tmp_path):
        runner = CliRunner()
        target_dir = tmp_path / "nested" / "dir" / "new_workspace"
        assert not target_dir.exists()

        with patch("sago.tui.app.SagoApp.run") as mock_app_run:
            result = runner.invoke(cli, ["tui", "-p", str(target_dir)])
            assert result.exit_code == 0
            assert target_dir.exists()
            assert target_dir.is_dir()
            assert Path(os.getcwd()).resolve() == target_dir.resolve()
            mock_app_run.assert_called_once()
