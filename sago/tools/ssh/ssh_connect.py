"""SSH Connect Tool - Establish SSH connections to remote hosts.

Cross-platform SSH connection management using paramiko.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SSHConnectArgs(BaseModel):
    """Arguments for SSHConnectTool."""

    hostname: str = Field(description="Remote host address")
    port: int = Field(default=22, description="SSH port (default: 22)")
    username: str = Field(description="SSH username")
    key_file: str | None = Field(default=None, description="Path to private key file")
    password: str | None = Field(default=None, description="SSH password (if not using key)")
    timeout: int = Field(default=30, description="Connection timeout in seconds")


class SSHConnectTool(BaseTool):
    """Tool for establishing SSH connections to remote hosts."""

    name = "ssh_connect"
    description = "Establish an SSH connection to a remote host using paramiko."
    args_model = SSHConnectArgs

    def _run(
        self,
        hostname: str,
        username: str,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        timeout: int = 30,
        **kwargs: Any,
    ) -> str:
        """Test SSH connection to a remote host.

        Args:
            hostname: Remote host address.
            username: SSH username.
            port: SSH port.
            key_file: Path to private key.
            password: SSH password.
            timeout: Connection timeout.

        Returns:
            Connection status and host information.
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
            "timeout": timeout,
        }

        if key_file:
            key_path = self._expand_path(key_file)
            connect_kwargs["key_filename"] = str(key_path)
        elif password:
            connect_kwargs["password"] = password

        try:
            client.connect(**connect_kwargs)

            # Get server info
            transport = client.get_transport()
            remote_addr = transport.getpeername() if transport else ("unknown", 0)

            # Get system info
            stdin, stdout, stderr = client.exec_command(
                "uname -a 2>/dev/null || systeminfo 2>/dev/null"
            )
            system_info = stdout.read().decode("utf-8", errors="replace").strip()

            client.close()

            return (
                f"SSH connection successful!\n"
                f"Host: {hostname}:{port}\n"
                f"User: {username}\n"
                f"Remote: {remote_addr[0]}:{remote_addr[1]}\n"
                f"System: {system_info}"
            )

        except paramiko.AuthenticationException:
            return f"Error: Authentication failed for {username}@{hostname}"
        except paramiko.SSHException as e:
            return f"Error: SSH connection failed: {e}"
        except Exception as e:
            return f"Error: {e}"
