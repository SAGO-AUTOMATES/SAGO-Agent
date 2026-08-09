"""Unit tests for permission system."""

import pytest

from sago.permissions import (
    PermissionManager,
    RiskLevel,
    TOOL_RISK_LEVELS,
    get_permission_manager,
)


@pytest.fixture
def pm():
    """Get a fresh permission manager."""
    return PermissionManager()


class TestRiskLevels:
    def test_all_tools_have_risk_levels(self):
        assert len(TOOL_RISK_LEVELS) >= 40

    def test_safe_tools(self):
        safe_tools = ["read_file", "glob_files", "grep_content", "env_info", "os_detector"]
        for tool in safe_tools:
            assert TOOL_RISK_LEVELS.get(tool) == RiskLevel.SAFE

    def test_low_risk_tools(self):
        low_tools = ["write_file", "edit_file", "file_operations"]
        for tool in low_tools:
            assert TOOL_RISK_LEVELS.get(tool) == RiskLevel.LOW

    def test_medium_risk_tools(self):
        medium_tools = ["execute_shell", "background_process"]
        for tool in medium_tools:
            assert TOOL_RISK_LEVELS.get(tool) == RiskLevel.MEDIUM

    def test_high_risk_tools(self):
        high_tools = ["ssh_connect", "ssh_command", "sudo_executor"]
        for tool in high_tools:
            assert TOOL_RISK_LEVELS.get(tool) == RiskLevel.HIGH

    def test_critical_risk_tools(self):
        critical_tools = ["spawn_agent"]
        for tool in critical_tools:
            assert TOOL_RISK_LEVELS.get(tool) == RiskLevel.CRITICAL


class TestPermissionManager:
    def test_get_risk_level(self, pm):
        assert pm.get_risk_level("read_file") == RiskLevel.SAFE
        assert pm.get_risk_level("sudo_executor") == RiskLevel.HIGH

    def test_default_risk_level(self, pm):
        assert pm.get_risk_level("unknown_tool") == RiskLevel.MEDIUM

    def test_is_blocked(self, pm):
        assert not pm.is_blocked("read_file")
        pm.config.blocked_tools.append("read_file")
        assert pm.is_blocked("read_file")

    def test_check_permission_safe(self, pm):
        allowed, reason = pm.check_permission("read_file")
        assert allowed is True
        assert "Auto-approved" in reason

    def test_check_permission_medium(self, pm):
        allowed, reason = pm.check_permission("execute_shell")
        assert allowed is False
        assert "requires approval" in reason

    def test_check_permission_high(self, pm):
        allowed, reason = pm.check_permission("sudo_executor")
        assert allowed is False
        assert "requires approval" in reason

    def test_check_permission_blocked(self, pm):
        pm.config.blocked_tools.append("test_tool")
        allowed, reason = pm.check_permission("test_tool")
        assert allowed is False
        assert "blocked" in reason.lower()

    def test_approve_tool(self, pm):
        pm.approve_tool("execute_shell", "session1")
        allowed, reason = pm.check_permission("execute_shell", session_id="session1")
        assert allowed is True
        assert "approved" in reason.lower()

    def test_deny_tool(self, pm):
        pm.deny_tool("execute_shell", "session1")
        allowed, reason = pm.check_permission("execute_shell", session_id="session1")
        assert allowed is False
        assert "denied" in reason.lower()

    def test_is_approved(self, pm):
        assert pm.is_approved("execute_shell") is None
        pm.approve_tool("execute_shell")
        assert pm.is_approved("execute_shell") is True
        pm.deny_tool("execute_shell")
        assert pm.is_approved("execute_shell") is False

    def test_session_isolation(self, pm):
        pm.approve_tool("execute_shell", "session1")
        assert pm.is_approved("execute_shell", "session1") is True
        assert pm.is_approved("execute_shell", "session2") is None


class TestPermissionConfig:
    def test_default_config(self, pm):
        assert pm.config.auto_approve_safe is True
        assert pm.config.auto_approve_low is True
        assert pm.config.require_approval_medium is True
        assert pm.config.require_approval_high is True
        assert pm.config.require_approval_critical is True
