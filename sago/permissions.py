"""Permission Manager for Sago tools.

Controls which tools can be executed based on risk level and user consent.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from sago.paths import get_sago_home

logger = logging.getLogger("sago.permissions")


class RiskLevel(Enum):
    """Tool risk levels."""

    SAFE = "safe"  # Read-only, no side effects
    LOW = "low"  # Minor side effects (write files, run tests)
    MEDIUM = "medium"  # Moderate side effects (shell commands, git operations)
    HIGH = "high"  # Dangerous operations (sudo, SSH, network changes)
    CRITICAL = "critical"  # Irreversible operations (delete data, system changes)


# Default risk levels for known tools
TOOL_RISK_LEVELS: dict[str, RiskLevel] = {
    # Safe - read only and internal agent delegation
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
    "repo_map": RiskLevel.SAFE,
    "delegate_to_agent": RiskLevel.SAFE,
    "agent_delegator": RiskLevel.SAFE,
    "git_blame": RiskLevel.SAFE,
    "secret_scanner": RiskLevel.SAFE,
    "web_search": RiskLevel.SAFE,
    "ast_grep": RiskLevel.SAFE,
    "sql_schema": RiskLevel.SAFE,
    "sql_migration": RiskLevel.SAFE,
    "platform_diagnostics": RiskLevel.SAFE,
    "search_symbols": RiskLevel.SAFE,
    "checkpoint_ops": RiskLevel.SAFE,
    # Low - minor side effects
    "write_file": RiskLevel.LOW,
    "edit_file": RiskLevel.LOW,
    "multi_replace_file": RiskLevel.LOW,
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
    "system_format": RiskLevel.CRITICAL,
    # Interactive - safe, just asks user
    "ask_question": RiskLevel.SAFE,
}


@dataclass
class PermissionConfig:
    """Permission configuration."""

    auto_approve_safe: bool = True
    auto_approve_low: bool = True
    require_approval_medium: bool = False
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
        self._lock = threading.Lock()
        self._yolo_sessions: set[str] = set()
        self._global_yolo: bool = False

    def set_global_yolo(self, enabled: bool) -> None:
        """Enable/disable YOLO mode globally."""
        with self._lock:
            self._global_yolo = enabled

    def set_yolo_mode(self, session_id: str, enabled: bool) -> None:
        """Enable/disable YOLO mode for a session."""
        with self._lock:
            if enabled:
                self._yolo_sessions.add(session_id)
            else:
                self._yolo_sessions.discard(session_id)

    def is_yolo(self, session_id: str = "default") -> bool:
        """Check if YOLO mode is enabled globally or for a session."""
        with self._lock:
            if self._global_yolo:
                return True
            if "default" in self._yolo_sessions:
                return True
            return session_id in self._yolo_sessions

    def _load_config(self) -> PermissionConfig:
        """Load permission config from disk."""
        config_path = get_sago_home() / "permissions.json"
        if config_path.exists():
            try:
                import json

                data = json.loads(config_path.read_text())
                return PermissionConfig(**data)
            except Exception as e:
                logger.debug("Failed to load permission config: %s", e)
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
                    "session_approvals": self.config.session_approvals,
                },
                indent=2,
            )
        )

    def get_risk_level(self, tool_name: str) -> RiskLevel:
        """Get the risk level for a tool."""
        risk = TOOL_RISK_LEVELS.get(tool_name, RiskLevel.HIGH)
        if tool_name not in TOOL_RISK_LEVELS:
            logger.warning("Unknown tool '%s' defaulted to HIGH risk", tool_name)
        else:
            logger.debug("Risk level for '%s': %s", tool_name, risk.value)
        return risk

    def is_blocked(self, tool_name: str) -> bool:
        """Check if a tool is blocked."""
        if tool_name in self.config.blocked_tools:
            logger.info("Tool '%s' is in blocked list", tool_name)
            return True
        if self.config.allowed_tools and tool_name not in self.config.allowed_tools:
            logger.info("Tool '%s' is not in allowed list", tool_name)
            return True
        return False

    def requires_approval(self, tool_name: str, args: dict[str, Any] | None = None) -> bool:
        """Check if a tool requires user approval before execution.

        Explicitly handles every risk level to avoid fallthrough bugs.
        """
        if self.is_blocked(tool_name):
            logger.info("Consent requested for '%s' — tool is blocked", tool_name)
            return True

        risk = self.get_risk_level(tool_name)

        if risk == RiskLevel.SAFE:
            result = not self.config.auto_approve_safe
        elif risk == RiskLevel.LOW:
            result = not self.config.auto_approve_low
        elif risk == RiskLevel.MEDIUM:
            result = self.config.require_approval_medium
        elif risk == RiskLevel.HIGH:
            result = self.config.require_approval_high
        elif risk == RiskLevel.CRITICAL:
            result = self.config.require_approval_critical
        else:
            result = True  # unknown risk -> require approval

        if result:
            logger.info("Consent requested for '%s' (risk: %s)", tool_name, risk.value)
        return result

    def approve_tool(self, tool_name: str, session_id: str = "default") -> bool:
        """Approve a tool for execution."""
        with self._lock:
            key = f"{tool_name}:{session_id}"
            self._approvals[key] = True
            self.config.session_approvals[key] = True
            self._save_config()
        logger.info("Tool '%s' approved for session '%s'", tool_name, session_id)
        return True

    def deny_tool(self, tool_name: str, session_id: str = "default") -> bool:
        """Deny a tool execution."""
        with self._lock:
            key = f"{tool_name}:{session_id}"
            self._approvals[key] = False
            self.config.session_approvals[key] = False
            self._save_config()
        logger.info("Tool '%s' denied for session '%s'", tool_name, session_id)
        return False

    def is_approved(self, tool_name: str, session_id: str = "default") -> bool | None:
        """Check if a tool has been approved. Returns None if not yet decided."""
        key = f"{tool_name}:{session_id}"
        with self._lock:
            if key in self._approvals:
                logger.debug(
                    "Permission cache hit for '%s' (session '%s'): %s",
                    tool_name,
                    session_id,
                    self._approvals[key],
                )
                return self._approvals[key]
            if key in self.config.session_approvals:
                logger.debug(
                    "Permission config hit for '%s' (session '%s'): %s",
                    tool_name,
                    session_id,
                    self.config.session_approvals[key],
                )
                return self.config.session_approvals[key]
        logger.debug("Permission cache miss for '%s' (session '%s')", tool_name, session_id)
        return None

    def check_permission(
        self, tool_name: str, args: dict[str, Any] | None = None, session_id: str = "default"
    ) -> tuple[bool, str]:
        """Check if a tool can be executed.

        Returns:
            Tuple of (allowed, reason).
        """
        risk = self.get_risk_level(tool_name)

        # YOLO mode bypasses all permission checks
        if self.is_yolo(session_id):
            logger.info("GRANTED '%s' (risk: %s) — YOLO mode", tool_name, risk.value)
            return True, "YOLO mode"

        if self.is_blocked(tool_name):
            logger.info("DENIED '%s' (risk: %s) — blocked", tool_name, risk.value)
            return False, f"Tool '{tool_name}' is blocked"

        # Explicit user approvals or denials take highest priority
        approved = self.is_approved(tool_name, session_id)
        if approved is True:
            logger.info("GRANTED '%s' (risk: %s) — user approved", tool_name, risk.value)
            return True, "User approved"
        if approved is False:
            logger.info("DENIED '%s' (risk: %s) — user denied", tool_name, risk.value)
            return False, "User denied"

        if not self.requires_approval(tool_name, args):
            logger.info("GRANTED '%s' (risk: %s) — auto-approved", tool_name, risk.value)
            return True, "Auto-approved"

        logger.info("DENIED '%s' (risk: %s) — requires approval", tool_name, risk.value)
        return (
            False,
            f"Tool '{tool_name}' requires approval (risk: {risk.value})",
        )


# Global instance
_permission_manager: PermissionManager | None = None
_permission_lock = threading.Lock()


def get_permission_manager() -> PermissionManager:
    """Get the global permission manager."""
    global _permission_manager
    if _permission_manager is None:
        with _permission_lock:
            if _permission_manager is None:
                _permission_manager = PermissionManager()
    return _permission_manager


def reset_permission_manager() -> PermissionManager:
    """Reset the global permission manager."""
    global _permission_manager
    with _permission_lock:
        _permission_manager = PermissionManager()
    return _permission_manager
