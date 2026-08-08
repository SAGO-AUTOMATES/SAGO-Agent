"""Glob Files Tool - Find files matching glob patterns.

Cross-platform file pattern matching.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class GlobFilesArgs(BaseModel):
    """Arguments for GlobFilesTool."""

    pattern: str = Field(description="Glob pattern (e.g., '**/*.py', 'src/**/*.ts')")
    path: str = Field(default=".", description="Directory to search in (default: current)")
    max_results: int = Field(default=100, description="Maximum number of results")


class GlobFilesTool(BaseTool):
    """Tool for finding files using glob patterns."""

    name = "glob_files"
    description = "Find files matching a glob pattern. Supports **, *, ? wildcards."
    args_model = GlobFilesArgs

    def _run(
        self,
        pattern: str,
        path: str = ".",
        max_results: int = 100,
        **kwargs: Any,
    ) -> str:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern to match.
            path: Directory to search in.
            max_results: Maximum results to return.

        Returns:
            List of matching file paths.
        """
        search_path = self._expand_path(path)

        if not search_path.exists():
            return f"Error: Directory not found: {search_path}"
        if not search_path.is_dir():
            return f"Error: Not a directory: {search_path}"

        matches = sorted(search_path.glob(pattern))
        files = [str(m.relative_to(search_path)) for m in matches if m.is_file()]
        dirs = [str(m.relative_to(search_path)) for m in matches if m.is_dir()]

        total = len(files) + len(dirs)
        truncated = total > max_results

        lines = []
        if dirs:
            lines.append(f"Directories ({len(dirs)}):")
            for d in dirs[:max_results]:
                lines.append(f"  {d}/")

        if files:
            lines.append(f"\nFiles ({len(files)}):")
            for f in files[:max_results - len(dirs)]:
                lines.append(f"  {f}")

        if truncated:
            lines.append(f"\n... ({total - max_results} more results truncated)")

        if not lines:
            return f"No matches found for pattern: {pattern} in {search_path}"

        return "\n".join(lines)
