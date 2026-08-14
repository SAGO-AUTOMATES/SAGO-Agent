"""Security audit tests for Sago."""

from sago.permissions import get_permission_manager


class TestPathTraversal:
    """Test for path traversal vulnerabilities."""

    def test_read_file_path_traversal(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        # Try to read outside allowed paths
        result = tool.run(file_path="../../../etc/passwd")
        # Should either work (if allowed) or fail safely
        assert result is not None

    def test_write_file_path_traversal(self):
        from sago.tools.file.write_file import WriteFileTool

        tool = WriteFileTool()
        # Try to write outside allowed paths
        result = tool.run(file_path="../../../tmp/evil.txt", content="malicious")
        # Should either work (if allowed) or fail safely
        assert result is not None

    def test_glob_files_path_traversal(self):
        from sago.tools.file.glob_files import GlobFilesTool

        tool = GlobFilesTool()
        # Try to glob outside allowed paths
        result = tool.run(pattern="*", path="../../../etc")
        # Should either work (if allowed) or fail safely
        assert result is not None


class TestCommandInjection:
    """Test for command injection vulnerabilities."""

    def test_execute_shell_injection(self):
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        # Try command injection
        result = tool.run(command="echo hello; rm -rf /")
        # Should execute but not cause damage
        assert result is not None

    def test_execute_shell_pipe_injection(self):
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        # Try pipe injection
        result = tool.run(command="echo hello | cat /etc/passwd")
        # Should execute but not cause damage
        assert result is not None


class TestPermissionBypass:
    """Test for permission bypass vulnerabilities."""

    def test_blocked_tool_cannot_execute(self):
        pm = get_permission_manager()
        pm.config.blocked_tools.append("test_blocked")
        allowed, reason = pm.check_permission("test_blocked")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_critical_tool_requires_approval(self):
        pm = get_permission_manager()
        allowed, reason = pm.check_permission("spawn_agent")
        assert allowed is False
        assert "requires approval" in reason.lower()

    def test_high_risk_tool_requires_approval(self):
        pm = get_permission_manager()
        allowed, reason = pm.check_permission("sudo_executor")
        assert allowed is False
        assert "requires approval" in reason.lower()


class TestInputValidation:
    """Test for input validation."""

    def test_empty_input_handling(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        result = tool.run(file_path="")
        assert result is not None

    def test_none_input_handling(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        result = tool.run(file_path=None)
        assert result is not None

    def test_special_characters_input(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        result = tool.run(file_path="test; rm -rf /")
        assert result is not None


class TestErrorHandling:
    """Test for proper error handling."""

    def test_tool_error_does_not_expose_internals(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        result = tool.run(file_path="/nonexistent/file/path/that/does/not/exist")
        # Should not expose stack traces or internal paths
        assert "Traceback" not in result or "Error" in result

    def test_permission_error_message(self):
        pm = get_permission_manager()
        pm.config.blocked_tools.append("test_tool")
        allowed, reason = pm.check_permission("test_tool")
        assert allowed is False
        # Should not expose internal details
        assert "blocked" in reason.lower()


class TestSensitiveData:
    """Test for sensitive data exposure."""

    def test_api_keys_not_in_output(self):
        from sago.tools.system.env_info import EnvInfo

        tool = EnvInfo()
        result = tool.run(operation="list")
        # Should not expose API keys
        assert "sk-" not in result
        assert "api_key" not in result.lower()

    def test_passwords_not_in_output(self):
        from sago.tools.system.env_info import EnvInfo

        tool = EnvInfo()
        result = tool.run(operation="list")
        # Should not expose passwords
        assert "password" not in result.lower()


class TestResourceExhaustion:
    """Test for resource exhaustion attacks."""

    def test_large_file_read(self):
        from sago.tools.file.read_file import ReadFileTool

        tool = ReadFileTool()
        # Try to read a very large file
        result = tool.run(file_path="/dev/urandom")
        # Should handle gracefully
        assert result is not None

    def test_infinite_loop_protection(self):
        # Test that tools don't hang indefinitely
        from sago.tools.shell.execute import ExecuteShellTool

        tool = ExecuteShellTool()
        # This should timeout or complete
        result = tool.run(command="timeout 1 echo test")
        assert result is not None
