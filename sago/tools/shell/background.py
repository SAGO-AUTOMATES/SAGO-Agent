"""Background Process Tool - Run long-running processes in background.

Cross-platform background process management.
"""

from __future__ import annotations

import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class BackgroundProcessArgs(BaseModel):
    """Arguments for BackgroundProcessTool."""

    command: str = Field(description="Command to run in background")
    cwd: str | None = Field(default=None, description="Working directory")
    log_file: str | None = Field(default=None, description="File to redirect output to")


class BackgroundProcessTool(BaseTool):
    """Tool for running processes in the background."""

    name = "background_process"
    description = "Run a command in the background and return its process ID."
    args_model = BackgroundProcessArgs

    def __init__(self) -> None:
        super().__init__()
        self._processes: dict[int, subprocess.Popen[bytes]] = {}

    def _run(
        self,
        command: str,
        cwd: str | None = None,
        log_file: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Start a background process.

        Args:
            command: Command to run.
            cwd: Working directory.
            log_file: Output log file.

        Returns:
            Process ID and status.
        """
        work_dir = None
        if cwd:
            work_dir = str(self._expand_path(cwd))

        stdout_dest = None
        if log_file:
            log_path = self._expand_path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_dest = open(log_path, "w")

        try:
            if self._is_windows():
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=work_dir,
                    stdout=stdout_dest or subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=work_dir,
                    stdout=stdout_dest or subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    preexec_fn=subprocess.os.setpgrp,
                )

            self._processes[process.pid] = process

            return (
                f"Background process started (PID: {process.pid})\n"
                f"Command: {command}\n"
                f"Working directory: {work_dir or 'default'}\n"
                f"Log file: {log_file or 'none'}\n\n"
                f"Use process_manager tool to check status or kill the process."
            )

        except Exception as e:
            return f"Error starting background process: {e}"

    def get_process(self, pid: int) -> subprocess.Popen[bytes] | None:
        """Get a running background process by PID."""
        return self._processes.get(pid)
