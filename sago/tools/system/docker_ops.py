"""Docker Operations Tool - Safe Docker CLI wrapper with auto-install.

Uses explicit argument lists (no shell injection). Auto-installs Docker if missing.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult
from sago.tools.ensure_dep import ensure_binary, is_available

_DOCKER_TIMEOUT = 120


class DockerOpsArgs(BaseModel):
    """Arguments for docker operations."""

    operation: str = Field(
        ...,
        description=(
            "Docker operation: ps, images, build, run, stop, rm, exec, logs, "
            "pull, push, inspect, stats, compose-up, compose-down, compose-logs, compose-ps"
        ),
    )
    args: list[str] = Field(default_factory=list, description="Arguments as a list")
    container: str = Field(default="", description="Container name/ID (for exec, logs, stop, rm)")
    image: str = Field(default="", description="Image name (for build, pull, push, run)")
    command: str = Field(default="", description="Command to run inside container")
    compose_file: str = Field(default="", description="Docker Compose file path")
    compose_project: str = Field(default="", description="Docker Compose project name")
    timeout: int = Field(default=_DOCKER_TIMEOUT, description="Command timeout in seconds")
    format_output: str = Field(
        default="", description="Output format (e.g. '{{json .}}' for inspect)"
    )
    dry_run: bool = Field(default=False, description="Add --dry-run where supported")
    auto_install: bool = Field(default=True, description="Auto-install Docker if missing")


class DockerOps(BaseTool):
    """Execute Docker operations safely with structured output."""

    name: str = "docker_ops"
    description: str = (
        "Execute Docker operations: ps, images, build, run, stop, rm, exec, logs, "
        "pull, push, inspect, stats, compose-up, compose-down, compose-logs, compose-ps. "
        "Uses explicit argument lists (no shell injection). Auto-installs Docker if missing."
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
        auto_install: bool = True,
        **extra: Any,
    ) -> ToolResult:
        op = (operation or "").strip().lower()

        # Ensure Docker is available
        if auto_install and not is_available("docker"):
            ok, msg = ensure_binary("docker", auto_install=True)
            if not ok:
                return ToolResult(output=msg, success=False, error="docker_not_found")
        elif not is_available("docker"):
            return ToolResult(
                output=(
                    "Docker not found.\n"
                    "Install Docker:\n"
                    "  Linux (Ubuntu/Debian): curl -fsSL https://get.docker.com | sh\n"
                    "  Linux (CentOS/RHEL): yum install -y docker-ce docker-ce-cli containerd.io\n"
                    "  macOS: brew install --cask docker\n"
                    "  Windows: winget install Docker.DockerDesktop\n\n"
                    "After install, start the Docker daemon."
                ),
                success=False,
                error="docker_not_found",
            )

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
                output=f"Docker {op} timed out after {timeout}s.", success=False, error="timeout"
            )
        except FileNotFoundError:
            return ToolResult(output="Docker not found.", success=False, error="docker_not_found")
        except Exception as e:
            return ToolResult(output=f"Failed to run docker {op}: {e}", success=False, error=str(e))

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return ToolResult(
                output=stderr or stdout or f"docker {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd},
            )

        metadata: dict[str, Any] = {"returncode": proc.returncode, "command": cmd}
        if stdout:
            try:
                parsed = json.loads(stdout)
                metadata["parsed"] = True
                if isinstance(parsed, list):
                    metadata["item_count"] = len(parsed)
            except (json.JSONDecodeError, ValueError):
                metadata["parsed"] = False

        return ToolResult(output=stdout or f"docker {op}: success", success=True, metadata=metadata)

    def _build_cmd(
        self,
        op,
        args,
        container,
        image,
        command,
        compose_file,
        compose_project,
        format_output,
        dry_run,
    ):
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
            cmd.extend(["run", "-d", "--rm"])
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
            cmd.extend(["compose", op.replace("compose-", "")])
            if compose_file:
                cmd.extend(["-f", compose_file])
            if compose_project:
                cmd.extend(["-p", compose_project])
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
