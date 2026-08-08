"""Docker Operations Tool - Docker commands wrapper."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DockerOpsArgs(BaseModel):
    """Arguments for docker operations."""

    operation: str = Field(
        description="Docker operation: ps, images, build, run, stop, rm, exec, logs, pull, push, compose-up, compose-down"
    )
    args: str = Field(default="", description="Additional arguments")
    cwd: str = Field(default=".", description="Working directory for compose operations")


class DockerOps(BaseTool):
    """Tool for executing docker operations."""

    name: str = "docker_ops"
    description: str = (
        "Execute docker operations: ps, images, build, run, stop, rm, exec, "
        "logs, pull, push, compose-up, compose-down."
    )
    args_model: type[BaseModel] = DockerOpsArgs

    def _run(
        self,
        operation: str,
        args: str = "",
        cwd: str = ".",
        **kwargs: Any,
    ) -> str:
        """Execute a docker operation."""
        cmd_map = {
            "ps": "docker ps {args}",
            "images": "docker images {args}",
            "build": "docker build {args}",
            "run": "docker run -d {args}",
            "stop": "docker stop {args}",
            "rm": "docker rm {args}",
            "exec": "docker exec -it {args}",
            "logs": "docker logs {args}",
            "pull": "docker pull {args}",
            "push": "docker push {args}",
            "compose-up": "docker compose up -d {args}",
            "compose-down": "docker compose down {args}",
            "compose-logs": "docker compose logs {args}",
            "compose-ps": "docker compose ps {args}",
        }

        if operation not in cmd_map:
            return f"Error: Invalid operation '{operation}'. Valid: {', '.join(sorted(cmd_map.keys()))}"

        cmd = cmd_map[operation].format(args=args)
        result = self._run_command(cmd, cwd=cwd, timeout=120)

        output = result.stdout if result.stdout else ""
        error = result.stderr if result.stderr else ""

        if result.returncode != 0:
            return f"Docker {operation} failed:\n{error}\n{output}"

        return f"Docker {operation}:\n{output}" if output else f"Docker {operation}: success"


def get_tool() -> type[DockerOps]:
    """Get the tool class."""
    return DockerOps
