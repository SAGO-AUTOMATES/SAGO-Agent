"""SSH Transfer Tool - Transfer files via SCP/SFTP.

Cross-platform file transfer to/from remote hosts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SSHTransferArgs(BaseModel):
    """Arguments for SSHTransferTool."""

    operation: Literal["upload", "download"] = Field(description="Transfer direction")
    source: str = Field(description="Source file path")
    destination: str = Field(description="Destination path (local or remote)")
    hostname: str = Field(description="Remote host address")
    username: str = Field(description="SSH username")
    port: int = Field(default=22, description="SSH port")
    key_file: str | None = Field(default=None, description="Path to private key file")
    password: str | None = Field(default=None, description="SSH password")


class SSHTransferTool(BaseTool):
    """Tool for transferring files via SCP/SFTP."""

    name = "ssh_transfer"
    description = "Transfer files to or from a remote host using SCP/SFTP."
    args_model = SSHTransferArgs

    def _run(
        self,
        operation: str,
        source: str,
        destination: str,
        hostname: str,
        username: str,
        port: int = 22,
        key_file: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Transfer files via SCP/SFTP.

        Args:
            operation: 'upload' or 'download'.
            source: Source file path.
            destination: Destination path.
            hostname: Remote host.
            username: SSH username.
            port: SSH port.
            key_file: Private key path.
            password: SSH password.

        Returns:
            Transfer status.
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
            sftp = client.open_sftp()

            if operation == "upload":
                local_path = str(self._expand_path(source))
                remote_path = destination
                sftp.put(local_path, remote_path)
                result = f"Uploaded {source} -> {username}@{hostname}:{destination}"
            else:
                local_path = str(self._expand_path(destination))
                remote_path = source
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                sftp.get(remote_path, local_path)
                result = f"Downloaded {username}@{hostname}:{source} -> {destination}"

            sftp.close()
            client.close()
            return result

        except paramiko.AuthenticationException:
            return f"Error: Authentication failed for {username}@{hostname}"
        except Exception as e:
            return f"Error during transfer: {e}"
