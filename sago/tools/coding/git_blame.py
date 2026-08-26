"""Git Blame Tool - Inspect file line history and author provenance."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.git_blame")


class GitBlameArgs(BaseModel):
    """Arguments for GitBlameTool."""

    path: str = Field(description="Relative or absolute path to the file")
    start_line: int = Field(default=1, description="Start line number (1-indexed)")
    end_line: int = Field(default=50, description="End line number (1-indexed)")


class GitBlameTool(BaseTool):
    """Tool to inspect git blame and authorship history for specific lines of code."""

    name = "git_blame"
    description = "Inspect git blame, author, commit hash, and timestamp for lines of code."
    args_model = GitBlameArgs
    risk_level = "safe"

    def _run(self, path: str, start_line: int = 1, end_line: int = 50, **kwargs: Any) -> str:
        target = Path(path)
        if not target.exists():
            return f"Error: File '{path}' does not exist."

        try:
            cmd = [
                "git",
                "blame",
                "-L",
                f"{start_line},{end_line}",
                "--date=short",
                str(target),
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if result.returncode != 0:
                return f"Git blame error: {result.stderr.strip() or result.stdout.strip()}"

            output = result.stdout.strip()
            if not output:
                return f"No blame history found for {path}:{start_line}-{end_line}"
            return output
        except Exception as exc:
            return f"Error executing git blame: {exc}"
