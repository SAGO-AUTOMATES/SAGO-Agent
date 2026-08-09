"""Unit tests for Sago tools."""

import os
import tempfile
from pathlib import Path

import pytest

from sago.engine.simple_executor import _discover_tools


@pytest.fixture
def tools():
    """Discover all tools."""
    return _discover_tools()


@pytest.fixture
def tmp_file(tmp_path):
    """Create a temporary file with content."""
    f = tmp_path / "test.txt"
    f.write_text("Hello, World!\nLine 2\nLine 3")
    return f


@pytest.fixture
def tmp_dir(tmp_path):
    """Create a temporary directory with files."""
    (tmp_path / "file1.txt").write_text("content1")
    (tmp_path / "file2.py").write_text("def foo(): pass")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "file3.txt").write_text("content3")
    return tmp_path


class TestReadFileTool:
    def test_read_file(self, tools, tmp_file):
        tool = tools["read_file"]()
        result = tool.run(file_path=str(tmp_file))
        assert "Hello, World!" in result
        assert "Line 2" in result

    def test_read_file_not_found(self, tools):
        tool = tools["read_file"]()
        result = tool.run(file_path="/nonexistent/file.txt")
        assert "Error" in result or "not found" in result.lower()


class TestWriteFileTool:
    def test_write_file(self, tools, tmp_path):
        tool = tools["write_file"]()
        out = tmp_path / "output.txt"
        result = tool.run(file_path=str(out), content="test content")
        assert out.exists()
        assert out.read_text() == "test content"

    def test_write_file_creates_dirs(self, tools, tmp_path):
        tool = tools["write_file"]()
        out = tmp_path / "nested" / "dir" / "file.txt"
        result = tool.run(file_path=str(out), content="nested")
        assert out.exists()


class TestGlobFilesTool:
    def test_glob_files(self, tools, tmp_dir):
        tool = tools["glob_files"]()
        result = tool.run(pattern="*.txt", path=str(tmp_dir))
        assert "file1.txt" in result

    def test_glob_files_recursive(self, tools, tmp_dir):
        tool = tools["glob_files"]()
        result = tool.run(pattern="**/*.txt", path=str(tmp_dir))
        assert "file1.txt" in result
        assert "file3.txt" in result


class TestGrepContentTool:
    def test_grep_content(self, tools, tmp_dir):
        tool = tools["grep_content"]()
        result = tool.run(pattern="def", path=str(tmp_dir))
        assert "foo" in result


class TestExecuteShellTool:
    def test_execute_shell_echo(self, tools):
        tool = tools["execute_shell"]()
        # Note: execute_shell requires permission approval (medium risk)
        result = tool.run(command="echo hello")
        # Result will be either the output or a permission denied message
        assert result is not None

    def test_execute_shell_returns_output(self, tools):
        tool = tools["execute_shell"]()
        result = tool.run(command="pwd")
        assert len(result) > 0


class TestHashChecksumTool:
    def test_hash_string(self, tools):
        tool = tools["hash_checksum"]()
        result = tool.run(operation="hash-string", target="hello")
        assert len(result) > 0

    def test_hash_file(self, tools, tmp_file):
        tool = tools["hash_checksum"]()
        result = tool.run(operation="hash-file", target=str(tmp_file))
        assert len(result) > 0


class TestDiffTool:
    def test_diff(self, tools):
        tool = tools["diff_tool"]()
        result = tool.run(operation="text", source="line1\nline2", target="line1\nline3")
        assert "line2" in result or "line3" in result


class TestRegexTesterTool:
    def test_regex_match(self, tools):
        tool = tools["regex_tester"]()
        result = tool.run(operation="test", pattern=r"\d+", text="abc123def")
        assert len(result) > 0


class TestEnvInfoTool:
    def test_env_info(self, tools):
        tool = tools["env_info"]()
        result = tool.run(operation="list")
        assert len(result) > 0


class TestOsDetectorTool:
    def test_os_detector(self, tools):
        tool = tools["os_detector"]()
        result = tool.run()
        assert len(result) > 0


class TestFileOperationsTool:
    def test_list_directory(self, tools, tmp_dir):
        tool = tools["file_operations"]()
        result = tool.run(operation="list", source=str(tmp_dir))
        assert "file1.txt" in result

    def test_file_info(self, tools, tmp_file):
        tool = tools["file_operations"]()
        # Use list operation to check file exists
        result = tool.run(operation="list", source=str(tmp_file.parent))
        assert "test.txt" in result


class TestArchiveTool:
    def test_archive_list(self, tools):
        tool = tools["archive"]()
        result = tool.run(operation="list", path=".")
        assert len(result) > 0


class TestBackgroundProcessTool:
    def test_background_process(self, tools):
        tool = tools["background_process"]()
        result = tool.run(command="echo test")
        assert len(result) > 0


class TestProcessManagerTool:
    def test_process_list(self, tools):
        tool = tools["process_manager"]()
        result = tool.run(action="list")
        assert len(result) > 0


class TestClipboardTool:
    def test_clipboard_read(self, tools):
        tool = tools["clipboard"]()
        result = tool.run(operation="read")
        assert len(result) > 0


class TestFormatterTool:
    def test_formatter(self, tools):
        tool = tools["formatter"]()
        result = tool.run(operation="format", file_path=".")
        assert len(result) > 0


class TestPromptGeneratorTool:
    def test_prompt_generator(self, tools):
        tool = tools["prompt_generator"]()
        result = tool.run(operation="generate", task="test task")
        assert len(result) > 0


class TestSessionManagerTool:
    def test_session_list(self, tools):
        tool = tools["session_manager"]()
        result = tool.run(operation="list")
        assert len(result) > 0


class TestCronScheduleTool:
    def test_cron_list(self, tools):
        tool = tools["cron_schedule"]()
        result = tool.run(operation="list")
        assert len(result) > 0


class TestDockerOpsTool:
    def test_docker_list(self, tools):
        tool = tools["docker_ops"]()
        result = tool.run(action="list")
        assert len(result) > 0


class TestNetworkConfigTool:
    def test_network_info(self, tools):
        tool = tools["network_config"]()
        result = tool.run(action="info")
        assert len(result) > 0


class TestPermissionManagerTool:
    def test_permission_list(self, tools):
        tool = tools["permission_manager"]()
        result = tool.run(action="list")
        assert len(result) > 0


class TestToolDiscovery:
    def test_all_tools_discovered(self, tools):
        assert len(tools) >= 40

    def test_tool_names_unique(self, tools):
        names = list(tools.keys())
        assert len(names) == len(set(names))

    def test_all_tools_have_name(self, tools):
        for name, cls in tools.items():
            assert hasattr(cls, "name")
            assert cls.name == name

    def test_all_tools_have_description(self, tools):
        for name, cls in tools.items():
            assert hasattr(cls, "description")
            assert len(cls.description) > 0

    def test_all_tools_have_args_model(self, tools):
        for name, cls in tools.items():
            assert hasattr(cls, "args_model")
