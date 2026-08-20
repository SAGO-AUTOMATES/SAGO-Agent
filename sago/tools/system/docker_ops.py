"""Docker Operations Tool - Safe Docker CLI wrapper with structured output."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_DOCKER_TIMEOUT = 120

# Operations that require explicit args (no implicit defaults)
NEEDS_ARGS = {"run", "exec", "build", "pull", "push", "stop", "rm"}


class DockerOpsArgs(BaseModel):
    """Arguments for docker operations."""

    operation: str = Field(
        ...,
        description=(
            "Docker operation: ps, images, build, run, stop, rm, exec, logs, "
            "pull, push, inspect, stats, compose-up, compose-down, compose-logs, compose-ps"
        ),
    )
    args: list[str] = Field(
        default_factory=list,
        description="Arguments as a list (e.g. ['nginx:latest', '-p', '8080:80'])",
    )
    container: str = Field(default="", description="Container name/ID (for exec, logs, stop, rm)")
    image: str = Field(default="", description="Image name (for build, pull, push, run)")
    command: str = Field(default="", description="Command to run inside container (for exec, run)")
    compose_file: str = Field(default="", description="Docker Compose file path (for compose ops)")
    compose_project: str = Field(default="", description="Docker Compose project name")
    timeout: int = Field(default=_DOCKER_TIMEOUT, description="Command timeout in seconds")
    format_output: str = Field(
        default="", description="Output format (e.g. '{{json .}}' for inspect)"
    )
    dry_run: bool = Field(default=False, description="Add --dry-run where supported")


class DockerOps(BaseTool):
    """Execute Docker operations safely with structured output."""

    name: str = "docker_ops"
    description: str = (
        "Execute Docker operations: ps, images, build, run, stop, rm, exec, logs, "
        "pull, push, inspect, stats, compose-up, compose-down, compose-logs, compose-ps. "
        "Uses explicit argument lists (no shell injection). Returns structured results."
    )
    category: ToolCategory = ToolCategory.SYSTEM
    args_model: type[BaseModel] | None = DockerOpsArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        operation: str,
        args: list[str] | None = None,
        container: str = "",
        image: str = "",
        command: str = "",
        compose_file: str = "",
        compose_project: str = "",
        timeout: int = _DOCKER_TIMEOUT,
        format_output: str = "",
        dry_run: bool = False,
        **extra: Any,
    ) -> ToolResult:
        op = (operation or "").strip().lower()

        # Build command safely with explicit args
        cmd = self._build_cmd(
            op,
            args or [],
            container,
            image,
            command,
            compose_file,
            compose_project,
            format_output,
            dry_run,
        )
        if isinstance(cmd, ToolResult):
            return cmd

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                output=f"Docker {op} timed out after {timeout}s.",
                success=False,
                error="timeout",
                metadata={"command": cmd, "timeout": timeout},
            )
        except FileNotFoundError:
            return ToolResult(
                output="Docker not found. Install Docker or ensure it's in PATH.",
                success=False,
                error="docker_not_found",
            )
        except Exception as e:
            return ToolResult(
                output=f"Failed to run docker {op}: {e}",
                success=False,
                error=str(e),
                metadata={"command": cmd},
            )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return ToolResult(
                output=stderr or stdout or f"docker {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd},
            )

        # Try to parse JSON output for structured metadata
        metadata: dict[str, Any] = {"returncode": proc.returncode, "command": cmd}
        if stdout:
            try:
                parsed = json.loads(stdout)
                metadata["parsed"] = True
                if isinstance(parsed, list):
                    metadata["item_count"] = len(parsed)
            except (json.JSONDecodeError, ValueError):
                metadata["parsed"] = False

        return ToolResult(
            output=stdout or f"docker {op}: success",
            success=True,
            metadata=metadata,
        )

    def _build_cmd(
        self,
        op: str,
        args: list[str],
        container: str,
        image: str,
        command: str,
        compose_file: str,
        compose_project: str,
        format_output: str,
        dry_run: bool,
    ) -> list[str] | ToolResult:
        """Build Docker command safely with explicit argument list."""
        cmd = ["docker"]

        if op == "ps":
            cmd.extend(["ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"])
            cmd.extend(args)
        elif op == "images":
            cmd.extend(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"])
            cmd.extend(args)
        elif op == "build":
            cmd.append("build")
            if dry_run:
                cmd.append("--dry-run")
            if image:
                cmd.extend(["-t", image])
            cmd.extend(args)
        elif op == "run":
            cmd.append("run")
            cmd.extend(["-d", "--rm"])
            if image:
                cmd.append(image)
            if command:
                cmd.extend(["sh", "-c", command])
            cmd.extend(args)
        elif op == "stop":
            cmd.append("stop")
            if container:
                cmd.append(container)
            cmd.extend(args)
        elif op == "rm":
            cmd.append("rm")
            if container:
                cmd.append(container)
            cmd.extend(args)
        elif op == "exec":
            cmd.extend(["exec", "-it"])
            if container:
                cmd.append(container)
            if command:
                cmd.extend(["sh", "-c", command])
            cmd.extend(args)
        elif op == "logs":
            cmd.extend(["logs", "--tail", "100"])
            if container:
                cmd.append(container)
            cmd.extend(args)
        elif op == "pull":
            cmd.append("pull")
            if image:
                cmd.append(image)
            cmd.extend(args)
        elif op == "push":
            cmd.append("push")
            if image:
                cmd.append(image)
            cmd.extend(args)
        elif op == "inspect":
            cmd.append("inspect")
            if format_output:
                cmd.extend(["-f", format_output])
            if container:
                cmd.append(container)
            cmd.extend(args)
        elif op == "stats":
            cmd.extend(["stats", "--no-stream"])
            if container:
                cmd.append(container)
            cmd.extend(args)
        elif op in ("compose-up", "compose-down", "compose-logs", "compose-ps"):
            cmd.extend(["compose"])
            compose_op = op.replace("compose-", "")
            cmd.append(compose_op)
            if compose_file:
                cmd.extend(["-f", compose_file])
            if compose_project:
                cmd.extend(["-p", compose_project])
            if compose_op == "up" and dry_run:
                cmd.append("--dry-run")
            cmd.extend(args)
        else:
            return ToolResult(
                output=f"Unknown operation: '{op}'. Valid: ps, images, build, run, stop, rm, exec, logs, pull, push, inspect, stats, compose-up, compose-down, compose-logs, compose-ps",
                success=False,
                error="unknown_operation",
            )

        return cmd


def get_tool() -> type[DockerOps]:
    """Get the tool class."""
    return DockerOps
