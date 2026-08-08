"""SSH Command Tool - Execute commands on remote hosts via SSH.

Cross-platform remote command execution.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SSHCommandArgs(BaseModel):
    """Arguments for SSHCommandTool."""

    hostname: str = Field(description="Remote host address")
    username: str = Field(description="SSH username")
    command: str = Field(description="Command to execute remotely")
    port: int = Field(default=22, description="SSH port")
    key_file: str | None = Field(default=None, description="Path to private key file")
    password: str | None = Field(default=None, description="SSH password")
    timeout: int = Field(default=60, description="Command timeout in seconds")


class SSHCommandTool(BaseTool):
    """Tool for executing commands on remote hosts via SSH."""

    name = "ssh_command"
    description = "Execute a command on a remote host via SSH and return the output."
    args_model = SSHCommandArgs

    def _run(
        self,
        hostname: str,
        username: str,
        command: str,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        timeout: int = 60,
        **kwargs: Any,
    ) -> str:
        """Execute a command on a remote host.

        Args:
            hostname: Remote host.
            username: SSH username.
            command: Command to execute.
            port: SSH port.
            key_file: Private key path.
            password: SSH password.
            timeout: Command timeout.

        Returns:
            Command output (stdout + stderr).
        """
        try:
            import paramiko
        except ImportError:
            return "Error: paramiko is not installed. Install with: pip install paramiko"

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": hostname,
            "port": port,
            "username": username,
            "timeout": 30,
        }

        if key_file:
            connect_kwargs["key_filename"] = str(self._expand_path(key_file))
        elif password:
            connect_kwargs["password"] = password

        try:
            client.connect(**connect_kwargs)

            # Execute command
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)

            exit_code = stdout.channel.recv_exit_status()
            stdout_text = stdout.read().decode("utf-8", errors="replace").strip()
            stderr_text = stderr.read().decode("utf-8", errors="replace").strip()

            client.close()

            result_parts = [
                f"Command: {command}",
                f"Host: {username}@{hostname}",
                f"Exit code: {exit_code}",
            ]

            if stdout_text:
                result_parts.append(f"\nSTDOUT:\n{stdout_text}")
            if stderr_text:
                result_parts.append(f"\nSTDERR:\n{stderr_text}")

            return "\n".join(result_parts)

        except paramiko.AuthenticationException:
            return f"Error: Authentication failed for {username}@{hostname}"
        except Exception as e:
            return f"Error executing remote command: {e}"
