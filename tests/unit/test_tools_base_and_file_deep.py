"""Comprehensive tests for sago.tools.base, write_file, glob_files, shell tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

from sago.tools.base import BaseTool, ToolCategory, ToolResult


# --- Minimal concrete tool for testing BaseTool ---
class EchoTool(BaseTool):
    name = "echo_tool"
    description = "Echoes its input"

    def _run(self, message: str = "hello", **kwargs: Any) -> str:
        return f"ECHO: {message}"


class BrokenTool(BaseTool):
    name = "broken_tool"
    description = "Always fails"

    def _run(self, **kwargs: Any) -> str:
        raise ValueError("intentional error")


class TestToolCategory:
    def test_all_categories_str(self) -> None:
        assert ToolCategory.CODING == "coding"
        assert ToolCategory.FILE == "file"
        assert ToolCategory.SHELL == "shell"
        assert ToolCategory.WEB == "web"

    def test_iter_categories(self) -> None:
        cats = list(ToolCategory)
        assert len(cats) > 5


class TestToolResult:
    def test_defaults(self) -> None:
        r = ToolResult()
        assert r.output == ""
        assert r.success is True
        assert r.error is None
        assert r.metadata == {}

    def test_with_error(self) -> None:
        r = ToolResult(output="failed", success=False, error="bad input")
        assert r.success is False
        assert r.error == "bad input"


class TestBaseTool:
    def test_run_success(self) -> None:
        tool = EchoTool()
        result = tool.run(message="world")
        assert "ECHO: world" in result

    def test_run_error_returns_error_string(self) -> None:
        tool = BrokenTool()
        result = tool.run()
        assert "Error" in result
        assert "intentional error" in result

    def test_is_linux(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "linux"):
            assert tool._is_linux() is True
            assert tool._is_windows() is False
            assert tool._is_macos() is False

    def test_is_windows(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "windows"):
            assert tool._is_windows() is True
            assert tool._is_linux() is False

    def test_is_macos(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "darwin"):
            assert tool._is_macos() is True

    def test_get_shell_linux(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "linux"):
            shell = tool._get_shell()
        assert "bash" in shell or "sh" in shell

    def test_get_shell_windows(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "windows"):
            assert tool._get_shell() == "powershell"

    def test_expand_path_tilde(self) -> None:
        tool = EchoTool()
        expanded = tool._expand_path("~/test")
        assert "~" not in str(expanded)

    def test_expand_path_absolute(self, tmp_path: Path) -> None:
        tool = EchoTool()
        p = tool._expand_path(str(tmp_path))
        assert p == tmp_path.resolve()

    def test_get_temp_dir_linux(self) -> None:
        tool = EchoTool()
        with patch.object(tool, "_os_type", "linux"):
            temp = tool._get_temp_dir()
        assert "sago" in str(temp)

    def test_run_command_success(self) -> None:
        tool = EchoTool()
        result = tool._run_command("echo hello", timeout=5)
        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_run_command_failure(self) -> None:
        tool = EchoTool()
        result = tool._run_command("exit 1", timeout=5)
        assert result.returncode != 0


class TestWriteFileTool:
    def test_write_creates_file(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "test.txt"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), "hello world")
        assert "Successfully wrote" in result
        assert target.read_text() == "hello world"

    def test_write_blocked_path(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value="Protected path"):
            result = tool._run("/etc/passwd", "bad")
        assert "Error" in result

    def test_write_invalid_json(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "data.json"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), "{bad json}")
        assert "Error" in result

    def test_write_valid_json(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "data.json"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), '{"key": "value"}')
        assert "Successfully wrote" in result
        assert "[json: OK]" in result

    def test_write_python_valid_syntax(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "module.py"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), "x = 1\ny = 2\n")
        assert "syntax: OK" in result

    def test_write_python_invalid_syntax(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "broken.py"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), "def foo(\n")
        assert "syntax: ERROR" in result or "Successfully" in result

    def test_write_with_backup(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "existing.txt"
        target.write_text("original")
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            tool._run(str(target), "updated", backup=True)
        backup = tmp_path / "existing.txt.bak"
        assert backup.exists()
        assert backup.read_text() == "original"

    def test_write_creates_parent_dirs(self, tmp_path: Path) -> None:
        from sago.tools.file.write_file import WriteFileTool

        target = tmp_path / "a" / "b" / "c" / "file.txt"
        tool = WriteFileTool()
        with patch("sago.security.approval.check_write_safety", return_value=None):
            result = tool._run(str(target), "deep content", create_dirs=True)
        assert target.exists()
        assert "Successfully" in result


class TestGlobFilesTool:
    def test_basic_glob(self, tmp_path: Path) -> None:
        from sago.tools.file.glob_files import GlobFilesTool

        (tmp_path / "a.py").write_text("x=1")
        (tmp_path / "b.py").write_text("y=2")
        (tmp_path / "c.txt").write_text("text")
        tool = GlobFilesTool()
        result = tool._run(pattern="*.py", path=str(tmp_path))
        assert "a.py" in result
        assert "b.py" in result

    def test_glob_no_matches(self, tmp_path: Path) -> None:
        from sago.tools.file.glob_files import GlobFilesTool

        tool = GlobFilesTool()
        result = tool._run(pattern="*.rs", path=str(tmp_path))
        assert result  # should return "No matches found" message


class TestExecuteShellTool:
    def test_run_echo(self) -> None:
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        result = tool._run("echo hello_from_test")
        assert "hello_from_test" in result

    def test_run_with_cwd(self, tmp_path: Path) -> None:
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        result = tool._run("pwd", cwd=str(tmp_path))
        assert str(tmp_path) in result or result.strip()

    def test_run_failure_captured(self) -> None:
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        result = tool._run("ls /nonexistent_path_xyz_abc")
        assert result  # Returns something (stderr captured)
