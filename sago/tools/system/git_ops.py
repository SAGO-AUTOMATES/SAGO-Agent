"""Git Operations Tool - Git commands wrapper."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class GitOpsArgs(BaseModel):
    """Arguments for git operations."""

    operation: str = Field(
        description="Git operation: status, log, diff, add, commit, push, pull, branch, checkout, stash, blame"
    )
    args: str = Field(default="", description="Additional arguments for the operation")
    cwd: str = Field(default=".", description="Working directory")


class GitOps(BaseTool):
    """Tool for executing git operations."""

    name: str = "git_ops"
    description: str = (
        "Execute git operations: status, log, diff, add, commit, push, pull, "
        "branch, checkout, stash, blame, and more."
    )
    args_model: type[BaseModel] = GitOpsArgs

    VALID_OPERATIONS = {
        "status", "log", "diff", "add", "commit", "push", "pull",
        "branch", "checkout", "stash", "blame", "remote", "tag",
        "merge", "rebase", "reset", "revert", "show", "diff-index",
    }

    def _run(
        self,
        operation: str,
        args: str = "",
        cwd: str = ".",
        **kwargs: Any,
    ) -> str:
        """Execute a git operation."""
        if operation not in self.VALID_OPERATIONS:
            return f"Error: Invalid operation '{operation}'. Valid: {', '.join(sorted(self.VALID_OPERATIONS))}"

        cmd = f"git {operation} {args}".strip()
        result = self._run_command(cmd, cwd=cwd, timeout=60)

        output = result.stdout if result.stdout else ""
        error = result.stderr if result.stderr else ""

        if result.returncode != 0:
            return f"Git {operation} failed (exit {result.returncode}):\n{error}\n{output}"

        return f"Git {operation}:\n{output}" if output else f"Git {operation}: success"


def get_tool() -> type[GitOps]:
    """Get the tool class."""
    return GitOps
