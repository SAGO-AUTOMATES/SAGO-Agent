"""Review Changes Tool - First-class code-review context for the agent.

Packages everything needed to review:
- uncommitted working-tree changes
- staged changes
- a specific commit
- changes vs a base branch
- an open GitHub PR (via `gh` when available)

into one structured, review-ready payload (status + stat + diff + commit log),
so agents don't have to improvise chains of raw git commands.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.vcs.review")


_GIT_TIMEOUT = 30
_DIFF_CHAR_CAP = 60_000


def _run_git(repo: Path, *args: str) -> tuple[bool, str]:
    try:
        res = subprocess.run(
            ["git", *args],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
        )
        if res.returncode != 0:
            return False, (res.stderr or "").strip() or f"git exit {res.returncode}"
        return True, res.stdout
    except FileNotFoundError:
        return False, "git executable not found on PATH"
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args[:2])}... timed out after {_GIT_TIMEOUT}s"
    except Exception as e:  # noqa: BLE001 - surfaced to caller as text
        return False, str(e)


class ReviewChangesArgs(BaseModel):
    """Arguments for review_changes."""

    target: str = Field(
        default="working_tree",
        description=(
            "What to review: "
            "'working_tree' (uncommitted changes vs HEAD), "
            "'staged' (index vs HEAD), "
            "'commit' (a single commit, use ref=<sha>), "
            "'branch' (commits/diff of current branch vs base, use base=<branch>), "
            "'pr' (open GitHub PR diff via 'gh'; optional pr_number)"
        ),
    )
    repo_path: str = Field(default=".", description="Path to the git repository")
    ref: str = Field(default="HEAD", description="Commit sha/ref for target='commit'")
    base: str = Field(default="main", description="Base branch for target='branch'")
    pr_number: int = Field(default=0, description="PR number for target='pr' (0 = current PR)")
    include_untracked: bool = Field(
        default=True,
        description="For working_tree: include untracked files list (contents of small ones)",
    )


class ReviewChangesTool(BaseTool):
    """Gather review-ready context for working tree, commit, branch, or PR."""

    name: str = "review_changes"
    description: str = (
        "Collect everything needed to REVIEW code changes in one call: changed-file list, "
        "diff stats and the actual diffs. Targets: uncommitted working-tree changes, staged "
        "changes, a specific commit, current branch vs its base, or an open GitHub PR. "
        "Use this tool whenever asked to review/audit/check pending work, a commit, or a PR."
    )
    category = None  # inferred from path (vcs)

    args_model: type[BaseModel] | None = ReviewChangesArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(**kwargs)
        return result.output

    def execute(
        self,
        target: str = "working_tree",
        repo_path: str = ".",
        ref: str = "HEAD",
        base: str = "main",
        pr_number: int = 0,
        include_untracked: bool = True,
        **extra: Any,
    ) -> Any:
        from sago.tools.base import ToolResult

        repo = Path(repo_path).resolve()
        if not (repo / ".git").exists():
            return ToolResult(
                output=f"Not a git repository: {repo}", success=False, error="no .git"
            )

        t = (target or "working_tree").strip().lower()
        sections: list[str] = [f"# Review target: {t}"]

        def _add(title: str, ok: bool, out: str, cap: int = _DIFF_CHAR_CAP) -> None:
            body = out.strip()
            if not ok:
                sections.append(f"\n## {title}\nERROR: {body}")
                return
            if not body:
                sections.append(f"\n## {title}\n(empty)")
                return
            if len(body) > cap:
                body = body[:cap] + f"\n… [truncated {len(out) - cap} chars]"
            sections.append(f"\n## {title}\n{body}")

        # Common context: short status + recent log
        ok, out = _run_git(repo, "status", "--porcelain", "--branch")
        _add("Status", ok, out)

        if t == "working_tree":
            ok, out = _run_git(repo, "diff", "--stat", "HEAD")
            _add("Diff stat (vs HEAD)", ok, out)
            ok, out = _run_git(repo, "diff", "HEAD")
            _add("Diff (unstaged+staged vs HEAD)", ok, out)
            if include_untracked:
                ok, out = _run_git(repo, "ls-files", "--others", "--exclude-standard")
                if ok and out.strip():
                    files = [f for f in out.splitlines() if f.strip()]
                    listing = "\n".join(files[:50])
                    extra_note = f"\n… (+{len(files) - 50} more)" if len(files) > 50 else ""
                    _add(
                        f"Untracked files ({len(files)})",
                        True,
                        f"{listing}{extra_note}",
                    )
        elif t == "staged":
            ok, out = _run_git(repo, "diff", "--cached", "--stat")
            _add("Staged stat", ok, out)
            ok, out = _run_git(repo, "diff", "--cached")
            _add("Staged diff", ok, out)
        elif t == "commit":
            sha = (ref or "HEAD").strip()
            ok, out = _run_git(repo, "show", "--stat", sha)
            _add(f"Commit {sha} (stat)", ok, out)
            ok, out = _run_git(repo, "log", "-1", "--format=fuller", sha)
            _add("Commit metadata", ok, out, cap=4_000)
            ok, out = _run_git(repo, "show", "--format=", sha)
            _add(f"Commit {sha} (full diff)", ok, out)
        elif t == "branch":
            base_ref = (base or "main").strip()
            ok, out = _run_git(repo, "log", "--oneline", f"{base_ref}..HEAD")
            _add(f"Commits ahead of {base_ref}", ok, out, cap=10_000)
            ok, out = _run_git(repo, "diff", "--stat", f"{base_ref}...HEAD")
            _add(f"Diff stat vs {base_ref}", ok, out)
            ok, out = _run_git(repo, "diff", f"{base_ref}...HEAD")
            _add(f"Full diff vs {base_ref}", ok, out)
        elif t == "pr":
            cmd = ["gh", "pr", "diff"]
            if pr_number:
                cmd.append(str(pr_number))
            try:
                res = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True, timeout=60)
                if res.returncode == 0:
                    _add("PR diff (gh)", True, res.stdout)
                else:
                    hint = (res.stderr or "").strip()
                    sections.append(
                        f"\n## PR diff (gh)\n'gh pr diff' failed: {hint}\n"
                        "Fallback: use git_operations with operation='log'/'diff' against "
                        "the PR branch, or authenticate the GitHub CLI."
                    )
            except FileNotFoundError:
                sections.append(
                    "\n## PR diff (gh)\nGitHub CLI ('gh') is not installed. "
                    "Install it or review via the PR branch with target='branch'."
                )
        else:
            return ToolResult(
                output=(
                    f"Unknown target '{target}'. Valid: working_tree, staged, commit, branch, pr"
                ),
                success=False,
                error="invalid target",
            )

        output = "\n".join(sections)
        return ToolResult(output=output[:200_000], success=True)


def get_tool() -> type[ReviewChangesTool]:
    """Get the tool class."""
    return ReviewChangesTool
