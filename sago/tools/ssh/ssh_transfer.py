"""SSH Transfer Tool - Transfer files via SCP/SFTP.

Cross-platform file transfer to/from remote hosts.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.ssh.ssh_transfer")


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
        logger.debug(
            "ssh_transfer called: operation=%s, source=%s, dest=%s, host=%s",
            operation,
            source,
            destination,
            hostname,
        )

        try:
            import paramiko
        except ImportError:
            logger.error("paramiko not installed")
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
            logger.info("SSH connected for transfer: %s@%s", username, hostname)
            sftp = client.open_sftp()

            if operation == "upload":
                local_path = str(self._expand_path(source))
                remote_path = destination
                logger.info(
                    "Uploading file: local=%s, remote=%s@%s:%s",
                    local_path,
                    username,
                    hostname,
                    remote_path,
                )
                sftp.put(local_path, remote_path)
                logger.info(
                    "Upload complete: %s -> %s@%s:%s", source, username, hostname, destination
                )
                result = f"Uploaded {source} -> {username}@{hostname}:{destination}"
            else:
                local_path = str(self._expand_path(destination))
                remote_path = source
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                logger.info(
                    "Downloading file: remote=%s@%s:%s, local=%s",
                    username,
                    hostname,
                    remote_path,
                    local_path,
                )
                sftp.get(remote_path, local_path)
                logger.info(
                    "Download complete: %s@%s:%s -> %s", username, hostname, source, destination
                )
                result = f"Downloaded {username}@{hostname}:{source} -> {destination}"

            sftp.close()
            client.close()
            return result

        except paramiko.AuthenticationException:
            logger.error("SSH authentication failed for transfer: %s@%s", username, hostname)
            return f"Error: Authentication failed for {username}@{hostname}"
        except Exception as e:
            logger.error(
                "SSH transfer failed: operation=%s, source=%s, error=%s", operation, source, e
            )
            return f"Error during transfer: {e}"
