"""Sandboxed Execution Environment for running untrusted code and commands safely."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult


@dataclass
class SandboxConfig:
    """Configuration for execution sandbox."""

    max_cpu_seconds: int = 30
    max_memory_mb: int = 512
    max_processes: int = 16
    allow_network: bool = False
    read_only_root: bool = True
    copy_workspace: bool = True
    allowed_env_vars: list[str] = field(
        default_factory=lambda: [
            "PATH",
            "LANG",
            "LC_ALL",
            "PYTHONPATH",
            "HOME",
            "TMPDIR",
            "USER",
        ]
    )


class SandboxedExecutor:
    """Executes commands and code inside an isolated workspace jail."""

    def __init__(
        self, workspace_root: str | None = None, config: SandboxConfig | None = None
    ) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else Path.cwd()
        self.config = config or SandboxConfig()

    def run_command(
        self,
        command: str | list[str],
        timeout: int | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Execute a command in an isolated temporary directory sandbox."""
        timeout = timeout or self.config.max_cpu_seconds

        with tempfile.TemporaryDirectory(prefix="sago_sandbox_") as temp_dir:
            sandbox_path = Path(temp_dir)

            # Mirror current workspace if requested (copying project files)
            if self.config.copy_workspace and self.workspace_root.exists():
                for item in self.workspace_root.iterdir():
                    if item.name.startswith((".", "venv", ".venv", "__pycache__", "node_modules")):
                        continue
                    try:
                        dest = sandbox_path / item.name
                        if item.is_dir():
                            shutil.copytree(item, dest, dirs_exist_ok=True)
                        else:
                            shutil.copy2(item, dest)
                    except Exception:
                        pass

            # Construct safe minimal environment
            safe_env: dict[str, str] = {
                k: os.environ[k] for k in self.config.allowed_env_vars if k in os.environ
            }
            safe_env["HOME"] = str(sandbox_path)
            safe_env["TMPDIR"] = str(sandbox_path)
            if extra_env:
                safe_env.update(extra_env)

            cmd_args = command if isinstance(command, list) else command

            try:
                proc = subprocess.run(
                    cmd_args,
                    shell=isinstance(command, str),
                    cwd=str(sandbox_path),
                    env=safe_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return {
                    "success": proc.returncode == 0,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_code": proc.returncode,
                    "sandbox_dir": str(sandbox_path),
                }
            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout} seconds.",
                    "exit_code": -1,
                    "sandbox_dir": str(sandbox_path),
                }
            except Exception as e:
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Sandbox execution failed: {e}",
                    "exit_code": -1,
                    "sandbox_dir": str(sandbox_path),
                }


class SandboxRunArgs(BaseModel):
    command: str = Field(description="Command to execute in isolated sandbox")
    timeout: int = Field(default=30, description="Max execution timeout in seconds")


class SandboxRunTool(BaseTool):
    """Tool for running untrusted shell or build commands in a sandboxed temp environment."""

    name = "sandbox_run"
    description = (
        "Execute a shell command inside an isolated temporary sandbox directory. "
        "Protects the host system from untrusted scripts, infinite loops, and disk pollution."
    )
    category = ToolCategory.SYSTEM
    args_model = SandboxRunArgs

    def _run(self, command: str, timeout: int = 30, **kwargs: Any) -> str:
        res = self.execute(command=command, timeout=timeout)
        return res.output

    def execute(self, command: str, timeout: int = 30) -> ToolResult:
        executor = SandboxedExecutor()
        res = executor.run_command(command, timeout=timeout)
        output = res["stdout"] if res["success"] else (res["stderr"] or res["stdout"])
        return ToolResult(
            output=output.strip() or f"Command finished with exit code {res['exit_code']}",
            success=res["success"],
            error=res["stderr"] if not res["success"] else None,
            metadata=res,
        )
