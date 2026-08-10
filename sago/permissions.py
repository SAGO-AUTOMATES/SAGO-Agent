"""Permission Manager for Sago tools.

Controls which tools can be executed based on risk level and user consent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sago.paths import get_sago_home


class RiskLevel(Enum):
    """Tool risk levels."""

    SAFE = "safe"  # Read-only, no side effects
    LOW = "low"  # Minor side effects (write files, run tests)
    MEDIUM = "medium"  # Moderate side effects (shell commands, git operations)
    HIGH = "high"  # Dangerous operations (sudo, SSH, network changes)
    CRITICAL = "critical"  # Irreversible operations (delete data, system changes)


# Default risk levels for known tools
TOOL_RISK_LEVELS: dict[str, RiskLevel] = {
    # Safe - read only
    "read_file": RiskLevel.SAFE,
    "glob_files": RiskLevel.SAFE,
    "grep_content": RiskLevel.SAFE,
    "code_analyzer": RiskLevel.SAFE,
    "log_analyzer": RiskLevel.SAFE,
    "os_detector": RiskLevel.SAFE,
    "env_info": RiskLevel.SAFE,
    "dns_lookup": RiskLevel.SAFE,
    "port_scan": RiskLevel.SAFE,
    "http_client": RiskLevel.SAFE,
    "pdf_reader": RiskLevel.SAFE,
    "regex_tester": RiskLevel.SAFE,
    "diff_tool": RiskLevel.SAFE,
    "hash_checksum": RiskLevel.SAFE,
    "text_summarizer": RiskLevel.SAFE,
    "clipboard": RiskLevel.SAFE,
    "session_manager": RiskLevel.SAFE,
    "web_crawler": RiskLevel.SAFE,
    "screenshot": RiskLevel.SAFE,
    "database_query": RiskLevel.SAFE,
    # Low - minor side effects
    "write_file": RiskLevel.LOW,
    "edit_file": RiskLevel.LOW,
    "file_operations": RiskLevel.LOW,
    "archive": RiskLevel.LOW,
    "data_processor": RiskLevel.LOW,
    "formatter": RiskLevel.LOW,
    "prompt_generator": RiskLevel.LOW,
    "git_ops": RiskLevel.LOW,
    # Medium - moderate side effects
    "execute_shell": RiskLevel.MEDIUM,
    "background_process": RiskLevel.MEDIUM,
    "test_runner": RiskLevel.MEDIUM,
    "linter": RiskLevel.MEDIUM,
    "debugger": RiskLevel.MEDIUM,
    "process_manager": RiskLevel.MEDIUM,
    "env_manager": RiskLevel.MEDIUM,
    "cron_schedule": RiskLevel.MEDIUM,
    "docker_ops": RiskLevel.MEDIUM,
    # High - dangerous operations
    "ssh_connect": RiskLevel.HIGH,
    "ssh_command": RiskLevel.HIGH,
    "ssh_transfer": RiskLevel.HIGH,
    "software_install": RiskLevel.HIGH,
    "sudo_executor": RiskLevel.HIGH,
    "permission_manager": RiskLevel.HIGH,
    "network_config": RiskLevel.HIGH,
    # Critical - irreversible operations
    "spawn_agent": RiskLevel.CRITICAL,
}


@dataclass
class PermissionConfig:
    """Permission configuration."""

    auto_approve_safe: bool = True
    auto_approve_low: bool = True
    require_approval_medium: bool = True
    require_approval_high: bool = True
    require_approval_critical: bool = True
    allowed_tools: list[str] = field(default_factory=list)
    blocked_tools: list[str] = field(default_factory=list)
    session_approvals: dict[str, bool] = field(default_factory=dict)


class PermissionManager:
    """Manages tool execution permissions."""

    def __init__(self) -> None:
        self.config = self._load_config()
        self._approvals: dict[str, bool] = {}

    def _load_config(self) -> PermissionConfig:
        """Load permission config from disk."""
        config_path = get_sago_home() / "permissions.json"
        if config_path.exists():
            try:
                import json

                data = json.loads(config_path.read_text())
                return PermissionConfig(**data)
            except Exception:
                pass
        return PermissionConfig()

    def _save_config(self) -> None:
        """Save permission config to disk."""
        import json

        config_path = get_sago_home() / "permissions.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps(
                {
                    "auto_approve_safe": self.config.auto_approve_safe,
                    "auto_approve_low": self.config.auto_approve_low,
                    "require_approval_medium": self.config.require_approval_medium,
                    "require_approval_high": self.config.require_approval_high,
                    "require_approval_critical": self.config.require_approval_critical,
                    "allowed_tools": self.config.allowed_tools,
                    "blocked_tools": self.config.blocked_tools,
                },
                indent=2,
            )
        )

    def get_risk_level(self, tool_name: str) -> RiskLevel:
        """Get the risk level for a tool."""
        return TOOL_RISK_LEVELS.get(tool_name, RiskLevel.MEDIUM)

    def is_blocked(self, tool_name: str) -> bool:
        """Check if a tool is blocked."""
        if tool_name in self.config.blocked_tools:
            return True
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            return True
        return False

    def requires_approval(self, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """Check if a tool requires user approval before execution."""
        if self.is_blocked(tool_name):
            return True

        risk = self.get_risk_level(tool_name)

        if risk == RiskLevel.SAFE and self.config.auto_approve_safe:
            return False
        if risk == RiskLevel.LOW and self.config.auto_approve_low:
            return False
        if risk == RiskLevel.MEDIUM and self.config.require_approval_medium:
            return True
        if risk == RiskLevel.HIGH and self.config.require_approval_high:
            return True
        if risk == RiskLevel.CRITICAL and self.config.require_approval_critical:
            return True

        return False

    def approve_tool(self, tool_name: str, session_id: str = "default") -> bool:
        """Approve a tool for execution."""
        key = f"{tool_name}:{session_id}"
        self._approvals[key] = True
        self.config.session_approvals[key] = True
        return True

    def deny_tool(self, tool_name: str, session_id: str = "default") -> bool:
        """Deny a tool execution."""
        key = f"{tool_name}:{session_id}"
        self._approvals[key] = False
        return False

    def is_approved(self, tool_name: str, session_id: str = "default") -> bool | None:
        """Check if a tool has been approved. Returns None if not yet decided."""
        key = f"{tool_name}:{session_id}"
        if key in self._approvals:
            return self._approvals[key]
        if key in self.config.session_approvals:
            return self.config.session_approvals[key]
        return None

    def check_permission(
        self, tool_name: str, args: dict[str, Any] | None = None, session_id: str = "default"
    ) -> tuple[bool, str]:
        """Check if a tool can be executed.

        Returns:
            Tuple of (allowed, reason).
        """
        if self.is_blocked(tool_name):
            return False, f"Tool '{tool_name}' is blocked"

        if not self.requires_approval(tool_name, args):
            return True, "Auto-approved"

        approved = self.is_approved(tool_name, session_id)
        if approved is True:
            return True, "User approved"
        if approved is False:
            return False, "User denied"

        return (
            False,
            f"Tool '{tool_name}' requires approval (risk: {self.get_risk_level(tool_name).value})",
        )


# Global instance
_permission_manager: PermissionManager | None = None


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = PermissionManager()
    return _permission_manager
