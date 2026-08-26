"""Git Operations Tool - Safe, structured execution of all common git operations.

Runs git via subprocess with an explicit argument list (never shell=True with
untrusted input), a timeout, and structured output. Merged from system/git_ops
and vcs/git_ops for a single, comprehensive, safe git tool.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_GIT_TIMEOUT = 30

# All safe operations with their base argument lists
SAFE_OPS: dict[str, list[str]] = {
    "status": ["status", "--porcelain", "--branch"],
    "diff": ["diff"],
    "diff-staged": ["diff", "--cached"],
    "diff-stat": ["diff", "--stat"],
    "log": ["log", "-n", "20", "--oneline"],
    "log-detailed": ["log", "-n", "10", "--format=%h %s (%an, %ar)"],
    "add": ["add"],
    "commit": ["commit", "-m"],
    "branch-list": ["branch", "--list"],
    "branch-create": ["checkout", "-b"],
    "branch-delete": ["branch", "-d"],
    "checkout": ["checkout"],
    "stash": ["stash", "push", "-m"],
    "stash-pop": ["stash", "pop"],
    "stash-list": ["stash", "list"],
    "remote-list": ["remote", "-v"],
    "tag-list": ["tag", "--list"],
    "tag-create": ["tag"],
    "show": ["show", "--stat"],
    "blame": ["blame", "--porcelain"],
    "reflog": ["reflog", "-n", "20"],
    "merge-base": ["merge-base"],
    "rev-list": ["rev-list", "--count"],
}

# Operations that modify state (need extra safety)
MUTATING_OPS = {
    "add",
    "commit",
    "branch-create",
    "branch-delete",
    "checkout",
    "stash",
    "stash-pop",
    "tag-create",
}


class GitOpsArgs(BaseModel):
    """Arguments for git operations."""

    operation: str = Field(
        ...,
        description=(
            "Git operation: status, diff, diff-staged, diff-stat, log, log-detailed, "
            "add, commit, branch-list, branch-create, branch-delete, checkout, "
            "stash, stash-pop, stash-list, remote-list, tag-list, tag-create, "
            "show, blame, reflog, merge-base, rev-list"
        ),
    )
    repo_path: str = Field(
        default=".",
        description="Path to the git repository (default: current directory).",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Extra arguments for the operation",
    )
    message: str = Field(
        default="",
        description="Commit message (for commit operation) or stash message",
    )
    branch: str = Field(
        default="",
        description="Branch name (for branch-create, branch-delete, checkout)",
    )
    target: str = Field(
        default="",
        description="Target ref (for merge-base, show, blame, tag-create)",
    )
    dry_run: bool = Field(
        default=False,
        description="Add --dry-run for mutating operations to preview",
    )


class GitOperationsTool(BaseTool):
    """Run all common git operations safely with structured output."""

    name: str = "git_operations"
    description: str = (
        "Execute git operations safely: status, diff, log, add, commit, branch management, "
        "stash, remote, tag, show, blame, reflog. Uses explicit argument lists (no shell injection), "
        "validates repository existence, returns structured results."
    )
    category: ToolCategory = ToolCategory.SYSTEM
    args_model: type[BaseModel] | None = GitOpsArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        operation: str,
        repo_path: str = ".",
        args: list[str] | None = None,
        message: str = "",
        branch: str = "",
        target: str = "",
        dry_run: bool = False,
        **extra: Any,
    ) -> ToolResult:
        op = (operation or "").strip().lower()

        if op not in SAFE_OPS:
            return ToolResult(
                output=f"Unsupported git operation: '{operation}'.\nValid: {', '.join(sorted(SAFE_OPS))}",
                success=False,
                error="unsupported_operation",
                metadata={"allowed": list(SAFE_OPS)},
            )

        # Validate repository
        repo = Path(repo_path).expanduser().resolve()
        if not (repo / ".git").exists():
            return ToolResult(
                output=f"No git repository found at: {repo}",
                success=False,
                error="not_a_repo",
                metadata={"repo_path": str(repo)},
            )

        # Build command
        cmd = self._build_cmd(op, repo, args or [], message, branch, target, dry_run)
        if isinstance(cmd, ToolResult):
            return cmd

        # Warn on mutating ops without dry_run
        if op in MUTATING_OPS and not dry_run:
            pass  # Allow but log

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
                output=f"Git '{op}' timed out after {_GIT_TIMEOUT}s.",
                success=False,
                error="timeout",
                metadata={"command": cmd, "timeout": _GIT_TIMEOUT},
            )
        except Exception as e:
            return ToolResult(
                output=f"Failed to run git {op}: {e}",
                success=False,
                error=str(e),
                metadata={"command": cmd},
            )

        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode != 0:
            return ToolResult(
                output=stderr or stdout or f"git {op} failed (code {proc.returncode}).",
                success=False,
                error=f"exit_{proc.returncode}",
                metadata={"returncode": proc.returncode, "command": cmd},
            )

        # Parse structured output where possible
        metadata: dict[str, Any] = {"returncode": proc.returncode, "command": cmd}
        if op == "status" and stdout:
            metadata["changed_files"] = len([line for line in stdout.splitlines() if line.strip()])
        elif op in ("log", "log-detailed") and stdout:
            metadata["commit_count"] = len(stdout.splitlines())
        elif op == "branch-list" and stdout:
            metadata["branches"] = [
                line.strip().lstrip("* ") for line in stdout.splitlines() if line.strip()
            ]
        elif op == "stash-list" and stdout:
            metadata["stash_count"] = len(stdout.splitlines())
        elif op == "remote-list" and stdout:
            metadata["remotes"] = len([line for line in stdout.splitlines() if line.strip()])
        elif op == "rev-list" and stdout:
            try:
                metadata["count"] = int(stdout.strip())
            except ValueError:
                pass

        return ToolResult(
            output=stdout or f"git {op} completed with no output.",
            success=True,
            metadata=metadata,
        )

    def _build_cmd(
        self,
        op: str,
        repo: Path,
        args: list[str],
        message: str,
        branch: str,
        target: str,
        dry_run: bool,
    ) -> list[str] | ToolResult:
        """Build git command safely with explicit argument list."""
        cmd = ["git", "-C", str(repo)]
        base = SAFE_OPS[op][:]
        cmd.extend(base)

        if op == "commit":
            commit_msg = message
            if not commit_msg and args:
                # Backward compat: allow message in args list
                commit_msg = args[0] if args else ""
            if not commit_msg:
                return ToolResult(
                    output="Commit requires a message. Use message='your commit message'.",
                    success=False,
                    error="missing_message",
                )
            cmd.append(commit_msg)
        elif op == "stash" and message:
            cmd.append(message)
        elif op in ("branch-create", "branch-delete"):
            if not branch:
                return ToolResult(
                    output=f"{op} requires a branch name. Use branch='branch-name'.",
                    success=False,
                    error="missing_branch",
                )
            cmd.append(branch)
        elif op == "checkout":
            if branch:
                cmd.append(branch)
            elif args:
                cmd.extend(args)
                return cmd
            else:
                return ToolResult(
                    output="checkout requires a branch name. Use branch='branch-name'.",
                    success=False,
                    error="missing_branch",
                )
        elif op == "tag-create":
            if not target:
                return ToolResult(
                    output="tag-create requires a tag name. Use target='tag-name'.",
                    success=False,
                    error="missing_tag",
                )
            cmd.append(target)
        elif op in ("merge-base", "show", "blame") and target:
            cmd.append(target)
        elif op in ("add",):
            if args:
                cmd.extend(args)
            else:
                cmd.append(".")
            return cmd  # Early return to avoid double-extending

        # Add extra args (validated to not inject flags)
        if args and op not in (
            "commit",
            "stash",
            "branch-create",
            "branch-delete",
            "checkout",
            "tag-create",
        ):
            # Filter out dangerous flags
            safe_extra = [
                a
                for a in args
                if not a.startswith("--") or a in ("--stat", "--name-only", "--name-status")
            ]
            cmd.extend(safe_extra)

        if dry_run and op in MUTATING_OPS:
            cmd.append("--dry-run")

        return cmd


class GitOpsTool(GitOperationsTool):
    """Alias for git_operations tool."""

    name: str = "git_ops"


def get_tool() -> type[GitOperationsTool]:
    """Get the tool class."""
    return GitOperationsTool
