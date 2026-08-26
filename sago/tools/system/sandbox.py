"""Sandboxed Execution Environment for running untrusted code and commands safely.

Uses Linux namespaces (unshare) for process isolation, resource limits for memory/CPU,
and network namespace blocking to provide actual security boundaries.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

logger = logging.getLogger("sago.tools.sandbox")


@dataclass
class SandboxConfig:
    """Configuration for execution sandbox."""

    max_cpu_seconds: int = 30
    max_memory_mb: int = 512
    max_processes: int = 16
    allow_network: bool = False
    read_only_root: bool = True
    copy_workspace: bool = True
    use_namespaces: bool = True  # Use Linux namespaces for isolation
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


def _check_namespace_support() -> bool:
    """Check if Linux namespace isolation is available."""
    try:
        result = subprocess.run(
            ["unshare", "--help"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_unshare_args(config: SandboxConfig) -> list[str]:
    """Build unshare command arguments for namespace isolation."""
    args = ["unshare"]

    # Always use mount namespace for filesystem isolation
    args.append("--mount")

    # Use PID namespace to limit process visibility
    args.append("--pid")

    # Use IPC namespace to isolate shared memory
    args.append("--ipc")

    # Use UTS namespace for hostname isolation
    args.append("--uts")

    # Network namespace for network isolation (unless explicitly allowed)
    if not config.allow_network:
        args.append("--net")

    # User namespace for privilege de-escalation (if available)
    try:
        # Check if user namespaces are enabled
        with open("/proc/sys/kernel/unprivileged_userns_clone") as f:
            if f.read().strip() == "1":
                args.append("--user")
    except (FileNotFoundError, PermissionError):
        logger.debug("User namespace not available for sandbox isolation")

    return args


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
        """Execute a command in an isolated temporary directory sandbox.

        Uses Linux namespaces for process isolation when available, falling back
        to resource limits and restricted environment for basic protection.
        """
        timeout = timeout or self.config.max_cpu_seconds
        use_namespaces = self.config.use_namespaces and _check_namespace_support()

        logger.debug(
            "sandbox run_command: command=%s, timeout=%d, use_namespaces=%s",
            command,
            timeout,
            use_namespaces,
        )

        with tempfile.TemporaryDirectory(prefix="sago_sandbox_") as temp_dir:
            sandbox_path = Path(temp_dir)
            logger.info("Sandbox created: path=%s, namespaces=%s", sandbox_path, use_namespaces)

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
                    except Exception as e:
                        logger.debug(
                            "Failed to copy workspace item %s to sandbox: %s", item.name, e
                        )
            safe_env: dict[str, str] = {
                k: os.environ[k] for k in self.config.allowed_env_vars if k in os.environ
            }
            safe_env["HOME"] = str(sandbox_path)
            safe_env["TMPDIR"] = str(sandbox_path)
            # Prevent environment leakage from parent process
            safe_env.pop("PYTHONPATH", None)
            safe_env.pop("LD_PRELOAD", None)
            safe_env.pop("LD_LIBRARY_PATH", None)
            if extra_env:
                safe_env.update(extra_env)

            cmd_args = command if isinstance(command, list) else command

            # Build the execution command with optional namespace isolation
            if use_namespaces:
                unshare_args = _build_unshare_args(self.config)
                # Wrap command to apply resource limits inside namespace
                inner_cmd = self._build_resource_limited_cmd(cmd_args, sandbox_path)
                full_cmd = unshare_args + ["--"] + inner_cmd
            else:
                # Fallback: use resource limits without namespaces
                full_cmd = self._build_resource_limited_cmd(cmd_args, sandbox_path)

            try:
                logger.debug("Sandbox executing: cmd=%s", full_cmd)
                proc = subprocess.run(
                    full_cmd,
                    shell=False,  # Never use shell with sandboxed commands
                    cwd=str(sandbox_path),
                    env=safe_env,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )

                # Check if namespace isolation failed due to permissions
                if (
                    use_namespaces
                    and proc.returncode != 0
                    and any(
                        msg in (proc.stderr or "").lower()
                        for msg in [
                            "operation not permitted",
                            "permission denied",
                            "cannot change root filesystem",
                        ]
                    )
                ):
                    logger.warning("Namespace isolation failed, falling back to resource limits")
                    # Fall back to non-namespace approach
                    full_cmd = self._build_resource_limited_cmd(cmd_args, sandbox_path)
                    proc = subprocess.run(
                        full_cmd,
                        shell=False,
                        cwd=str(sandbox_path),
                        env=safe_env,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                    )
                    use_namespaces = False

                logger.info(
                    "Sandbox execution completed: exit_code=%d, isolated=%s",
                    proc.returncode,
                    use_namespaces,
                )
                return {
                    "success": proc.returncode == 0,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_code": proc.returncode,
                    "sandbox_dir": str(sandbox_path),
                    "isolated": use_namespaces,
                }
            except subprocess.TimeoutExpired:
                logger.warning("Sandbox execution timed out: timeout=%d", timeout)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Execution timed out after {timeout} seconds.",
                    "exit_code": -1,
                    "sandbox_dir": str(sandbox_path),
                    "isolated": use_namespaces,
                }
            except Exception as e:
                logger.error("Sandbox execution failed: error=%s", e)
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Sandbox execution failed: {e}",
                    "exit_code": -1,
                    "sandbox_dir": str(sandbox_path),
                    "isolated": use_namespaces,
                }

    def _build_resource_limited_cmd(
        self, cmd_args: list[str] | str, sandbox_path: Path
    ) -> list[str]:
        """Build command with resource limits applied.

        Uses bash -c wrapper to apply ulimit restrictions when running
        with namespaces, or applies limits directly via preexec_fn equivalent.
        """
        # Create a wrapper script that applies resource limits
        limits_script = f"""#!/bin/bash
# Apply resource limits
ulimit -v {self.config.max_memory_mb * 1024}  # Virtual memory limit
ulimit -u {self.config.max_processes}  # Process limit
ulimit -t {self.config.max_cpu_seconds}  # CPU time limit

# Execute the actual command
exec "$@"
"""
        limits_path = sandbox_path / ".sandbox_limits.sh"
        limits_path.write_text(limits_script)
        os.chmod(str(limits_path), 0o755)

        if isinstance(cmd_args, str):
            # For shell commands, wrap in bash -c with limits
            return ["bash", str(limits_path), "bash", "-c", cmd_args]
        else:
            # For list commands, pass directly
            return ["bash", str(limits_path)] + cmd_args


class SandboxRunArgs(BaseModel):
    command: str = Field(description="Command to execute in isolated sandbox")
    timeout: int = Field(default=30, description="Max execution timeout in seconds")


class SandboxRunTool(BaseTool):
    """Tool for running untrusted shell or build commands in a sandboxed temp environment."""

    name = "sandbox_run"
    description = (
        "Execute a shell command inside an isolated temporary sandbox directory with process isolation. "
        "Uses Linux namespaces for network/process isolation, resource limits for memory/CPU, "
        "and restricted environment to protect the host system. Network access is blocked by default."
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
        isolation_info = " (namespace isolated)" if res.get("isolated") else " (resource limited)"
        return ToolResult(
            output=output.strip()
            or f"Command finished with exit code {res['exit_code']}{isolation_info}",
            success=res["success"],
            error=res["stderr"] if not res["success"] else None,
            metadata=res,
        )
