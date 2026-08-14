"""Sudo Executor Tool - Execute commands with elevated privileges.

Cross-platform privilege escalation support.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SudoExecutorArgs(BaseModel):
    """Arguments for SudoExecutorTool."""

    command: str = Field(description="Command to execute with elevated privileges")
    password: str | None = Field(default=None, description="Sudo password (if required)")
    timeout: int = Field(default=60, description="Timeout in seconds")


class SudoExecutorTool(BaseTool):
    """Tool for executing commands with elevated privileges."""

    name = "sudo_executor"
    description = "Execute commands with elevated privileges (sudo/admin)."
    args_model = SudoExecutorArgs

    def _run(
        self,
        command: str,
        password: str | None = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> str:
        """Execute a command with elevated privileges.

        Args:
            command: Command to execute.
            password: Sudo password.
            timeout: Timeout in seconds.

        Returns:
            Command output.
        """
        if self._is_windows():
            return self._run_windows(command, password, timeout)
        else:
            return self._run_unix(command, password, timeout)

    def _run_windows(self, command: str, password: str | None, timeout: int) -> str:
        """Execute command with admin privileges on Windows."""
        # Use PowerShell Start-Process with RunAs
        ps_cmd = (
            f"Start-Process powershell -ArgumentList '-Command', "
            f"'{command}' -Verb RunAs -Wait -PassThru"
        )

        result = self._run_command(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            timeout=timeout,
        )

        output_parts = [f"Command (elevated): {command}"]
        if result.stdout:
            output_parts.append(f"\nOutput:\n{result.stdout.strip()}")
        if result.stderr:
            output_parts.append(f"\nErrors:\n{result.stderr.strip()}")

        return "\n".join(output_parts)

    def _run_unix(self, command: str, password: str | None, timeout: int) -> str:
        """Execute command with sudo on Unix systems."""
        import subprocess

        if password:
            # Use printf to avoid shell interpretation of password
            import shlex

            safe_password = shlex.quote(password)
            safe_command = shlex.quote(command)
            full_cmd = f"printf %s {safe_password} | sudo -S {safe_command}"
        else:
            import shlex

            full_cmd = f"sudo {shlex.quote(command)}"

        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )

            output_parts = [f"Command (elevated): {command}"]
            if result.stdout:
                output_parts.append(f"\nOutput:\n{result.stdout.strip()}")
            if result.stderr:
                # Remove password prompt from stderr
                stderr = result.stderr.replace("[sudo] password for", "").strip()
                if stderr:
                    output_parts.append(f"\nErrors:\n{stderr}")

            if result.returncode != 0:
                output_parts.append(f"\nExit code: {result.returncode}")

            return "\n".join(output_parts)

        except subprocess.TimeoutExpired:
            return f"Error: Command timed out after {timeout} seconds"
        except Exception as e:
            return f"Error executing elevated command: {e}"
