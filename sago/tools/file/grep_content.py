"""Grep Content Tool - Search file contents using regex.

Cross-platform content search with regex support.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tools.file.grep_content")


class GrepContentArgs(BaseModel):
    """Arguments for GrepContentTool."""

    pattern: str = Field(description="Regex pattern to search for")
    path: str = Field(default=".", description="Directory or file to search in")
    include: str | None = Field(default=None, description="File pattern to include (e.g., '*.py')")
    exclude: str | None = Field(default=None, description="File pattern to exclude")
    max_results: int = Field(default=100, description="Maximum matches to return")
    context_lines: int = Field(default=0, description="Number of context lines around matches")
    max_file_size: int = Field(
        default=1048576, description="Maximum file size in bytes to search (default: 1MB)"
    )


class GrepContentTool(BaseTool):
    """Tool for searching file contents using regex patterns."""

    name = "grep_content"
    description = "Search file contents using regex patterns. Returns matching lines with context."
    args_model = GrepContentArgs

    def _run(
        self,
        pattern: str,
        path: str = ".",
        include: str | None = None,
        exclude: str | None = None,
        max_results: int = 100,
        context_lines: int = 0,
        max_file_size: int = 1048576,
        **kwargs: Any,
    ) -> str:
        """Search file contents using regex.

        Args:
            pattern: Regex pattern to search for.
            path: Directory or file to search.
            include: File pattern to include.
            exclude: File pattern to exclude.
            max_results: Maximum matches.
            context_lines: Context lines around matches.

        Returns:
            Matching lines with file locations.
        """
        search_path = self._expand_path(path)

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"Error: Invalid regex pattern: {e}"

        if not search_path.exists():
            return f"Error: Path not found: {search_path}"

        matches: list[str] = []
        files_searched = 0

        if search_path.is_file():
            files_to_search = [search_path]
        else:
            glob_pattern = "**/*"
            if include:
                glob_pattern = f"**/{include}"
            files_to_search = [f for f in search_path.glob(glob_pattern) if f.is_file()]

        for file_path in files_to_search:
            if exclude and file_path.match(exclude):
                continue

            # Skip files that are too large
            try:
                if file_path.stat().st_size > max_file_size:
                    continue
            except (OSError, PermissionError):
                continue

            files_searched += 1
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception as e:
                log_error("Failed to read file during grep", e, context={"path": str(file_path)})
                continue

            for i, line in enumerate(lines):
                if regex.search(line):
                    rel_path = (
                        file_path.relative_to(search_path) if search_path.is_dir() else file_path
                    )
                    match_info = f"{rel_path}:{i + 1}: {line.strip()}"
                    matches.append(match_info)

                    if context_lines > 0:
                        start = max(0, i - context_lines)
                        end = min(len(lines), i + context_lines + 1)
                        for j in range(start, end):
                            if j != i:
                                matches.append(f"  {j + 1}: {lines[j].strip()}")

                    if len(matches) >= max_results:
                        break

            if len(matches) >= max_results:
                break

        if not matches:
            return f"No matches found for pattern '{pattern}' in {search_path} ({files_searched} files searched)"

        header = f"Found {len(matches)} match(es) in {files_searched} files:\n\n"
        return header + "\n".join(matches[:max_results])
