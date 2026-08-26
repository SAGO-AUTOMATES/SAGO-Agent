"""Execute Shell Command Tool - Run shell commands cross-platform.

Supports Windows (PowerShell), macOS/Linux (bash/zsh).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.shell.execute")


class ExecuteShellArgs(BaseModel):
    """Arguments for ExecuteShellTool."""

    command: str = Field(description="Shell command to execute")
    cwd: str | None = Field(default=None, description="Working directory (default: current)")
    timeout: int = Field(default=300, description="Timeout in seconds (default: 300)")


class ExecuteShellTool(BaseTool):
    """Tool for executing shell commands across platforms."""

    name = "execute_shell"
    description = (
        "Execute a shell command and return its output. Works on Windows, macOS, and Linux."
    )
    args_model = ExecuteShellArgs

    def _run(
        self,
        command: str,
        cwd: str | None = None,
        timeout: int = 300,
        **kwargs: Any,
    ) -> str:
        """Execute a shell command.

        Args:
            command: Command to execute.
            cwd: Working directory.
            timeout: Timeout in seconds.

        Returns:
            Command output (stdout + stderr).
        """
        logger.debug("execute_shell called: command=%s, cwd=%s, timeout=%d", command, cwd, timeout)

        # Platform-specific command wrapping
        if self._is_windows():
            # Use PowerShell on Windows
            full_command = f"powershell -NoProfile -Command {command}"
        else:
            full_command = command

        # Safety check against catastrophic destructive commands
        dangerous_patterns = [
            "rm -rf /",
            "rm -rf /*",
            "rm -rf ~",
            ":(){ :|:& };:",
            "mkfs.",
            "> /dev/sda",
            "> /dev/nvme",
            "dd if=/dev/zero of=/dev/sd",
        ]
        cmd_lower = command.strip().lower()
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                logger.warning(
                    "Safety guard rejected command: pattern=%s, command=%s", pattern, command
                )
                return f"Error: Command rejected by safety guard: '{pattern}' is forbidden."

        # Determine working directory
        work_dir = None
        if cwd:
            work_dir = self._expand_path(cwd)
            if not work_dir.exists():
                logger.warning("Working directory not found: %s", work_dir)
                return f"Error: Working directory not found: {work_dir}"

        # Validate timeout
        if timeout <= 0:
            timeout = 300
        timeout = min(timeout, 3600)  # Cap at 1 hour

        logger.info("Executing shell command: %s (timeout=%d, cwd=%s)", command, timeout, work_dir)

        try:
            result = self._run_command(
                full_command,
                timeout=timeout,
                cwd=work_dir,
                shell=True,
                capture_output=True,
            )

            output_parts = []
            if result.stdout:
                output_parts.append(result.stdout.strip())
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr.strip()}")

            if result.returncode != 0:
                output_parts.append(f"\nExit code: {result.returncode}")

            logger.debug(
                "Command completed: returncode=%d, stdout_len=%d, stderr_len=%d",
                result.returncode,
                len(result.stdout) if result.stdout else 0,
                len(result.stderr) if result.stderr else 0,
            )

            if not output_parts:
                logger.info("Command executed successfully (no output)")
                return "Command executed successfully (no output)"

            return "\n".join(output_parts)

        except TimeoutError:
            logger.warning("Command timed out after %d seconds: %s", timeout, command)
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            logger.error("Command execution failed: command=%s, error=%s", command, e)
            return f"Error executing command: {e}"
