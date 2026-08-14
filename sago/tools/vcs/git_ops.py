"""Git Operations Tool - Safe, structured execution of common git operations.

Runs git via subprocess with an explicit argument list (never shell=True with
untrusted input) and a timeout so a hung command cannot block the agent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_GIT_TIMEOUT = 30


class GitOpsArgs(BaseModel):
    operation: str = Field(
        ...,
        description="Git operation to run: status, diff, log, add, commit, branch.",
    )
    repo_path: str = Field(
        default=".",
        description="Path to the git repository (default: current directory).",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Extra arguments for the operation (e.g. files to add, commit message).",
    )


class GitOperationsTool(BaseTool):
    """Run common git operations (status, diff, log, add, commit, branch) safely."""

    name: str = "git_operations"
    description: str = (
        "Execute common git operations (status, diff, log, add, commit, branch list) "
        "in a repository using a safe, non-shell subprocess with a timeout. "
        "Returns structured results and handles errors gracefully."
    )
    category: ToolCategory = ToolCategory.SYSTEM
    args_model: type[BaseModel] | None = GitOpsArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(
            operation=kwargs.get("operation", ""),
            repo_path=kwargs.get("repo_path", "."),
            args=kwargs.get("args", []),
        )
        return result.output

    def execute(
        self,
        operation: str,
        repo_path: str = ".",
        args: list[str] | None = None,
    ) -> ToolResult:
        op = (operation or "").strip().lower()
        allowed = {
            "status": ["status", "--porcelain", "--branch"],
            "diff": ["diff"],
            "log": ["log", "-n", "20", "--oneline"],
            "add": ["add"],
            "commit": ["commit", "-m"],
            "branch": ["branch", "--list"],
        }
        if op not in allowed:
            return ToolResult(
                output=f"Unsupported git operation: '{operation}'. Allowed: {', '.join(allowed)}",
                success=False,
                error="unsupported_operation",
                metadata={"allowed": list(allowed)},
            )

        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists():
            return ToolResult(
                output=f"No git repository found at: {repo}",
                success=False,
                error="not_a_repo",
                metadata={"repo_path": str(repo)},
            )

        extra = [str(a) for a in (args or [])]
        cmd = ["git", "-C", str(repo), *allowed[op], *extra]

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                output=f"Git operation '{op}' timed out after {_GIT_TIMEOUT}s.",
                success=False,
                error="timeout",
                metadata={"command": cmd},
            )
        except Exception as e:  # pragma: no cover - defensive
            return ToolResult(
                output=f"Failed to run git {op}: {e}",
                success=False,
                error=str(e),
                metadata={"command": cmd},
            )

        if proc.returncode != 0:
            return ToolResult(
                output=proc.stderr.strip() or f"git {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd},
            )

        return ToolResult(
            output=proc.stdout.strip() or f"git {op} completed with no output.",
            success=True,
            metadata={"returncode": proc.returncode, "command": cmd},
        )
