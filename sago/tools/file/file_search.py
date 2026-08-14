"""File Search Tool - Locate files by name pattern and/or content regex.

Uses pathlib glob for name matching and optional regex content scanning,
respecting a max depth and a set of ignored directories.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool, ToolCategory, ToolResult

_DEFAULT_IGNORE = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".tox",
    "dist",
    "build",
}


class FileSearchArgs(BaseModel):
    pattern: str = Field(
        default="*",
        description="Filename glob pattern (e.g. '*.py', 'config.*').",
    )
    content_regex: str | None = Field(
        default=None,
        description="Optional regex to search inside matched files.",
    )
    root: str = Field(
        default=".",
        description="Root directory to start the search from.",
    )
    max_depth: int = Field(
        default=8,
        description="Maximum directory descent depth from root.",
    )
    ignore: list[str] = Field(
        default_factory=list,
        description="Additional directory names to ignore.",
    )


class FileSearchTool(BaseTool):
    """Search the filesystem for files by name and/or content with depth limits."""

    name: str = "file_search"
    description: str = (
        "Search for files by glob name pattern and optionally by content regex, "
        "respecting a max-depth and ignoring common noise directories "
        "(.git, node_modules, .venv, etc.). Returns matching paths."
    )
    category: ToolCategory = ToolCategory.FILE
    args_model: type[BaseModel] | None = FileSearchArgs

    def _run(self, **kwargs: Any) -> str:
        result = self.execute(
            pattern=kwargs.get("pattern", "*"),
            content_regex=kwargs.get("content_regex"),
            root=kwargs.get("root", "."),
            max_depth=kwargs.get("max_depth", 8),
            ignore=kwargs.get("ignore", []),
        )
        return result.output

    def execute(
        self,
        pattern: str = "*",
        content_regex: str | None = None,
        root: str = ".",
        max_depth: int = 8,
        ignore: list[str] | None = None,
    ) -> ToolResult:
        ignore_dirs = set(_DEFAULT_IGNORE) | {i for i in (ignore or [])}
        base = Path(root).expanduser().resolve()

        if not base.exists():
            return ToolResult(
                output=f"Root path does not exist: {base}",
                success=False,
                error="missing_root",
                metadata={"root": str(base)},
            )

        compiled: re.Pattern[str] | None = None
        if content_regex:
            try:
                compiled = re.compile(content_regex)
            except re.error as e:
                return ToolResult(
                    output=f"Invalid content_regex: {e}",
                    success=False,
                    error=str(e),
                    metadata={"content_regex": content_regex},
                )

        matches: list[str] = []
        try:
            for path in base.glob("**/" + pattern):
                if not path.is_file():
                    continue
                rel = path.relative_to(base)
                if any(part in ignore_dirs for part in rel.parts):
                    continue
                depth = len(rel.parts) - 1
                if depth > max_depth:
                    continue
                if compiled is not None:
                    try:
                        text = path.read_text("utf-8", errors="replace")
                    except Exception:
                        continue
                    if not compiled.search(text):
                        continue
                matches.append(str(path))
        except Exception as e:  # pragma: no cover - defensive
            return ToolResult(
                output=f"File search failed: {e}",
                success=False,
                error=str(e),
                metadata={"root": str(base)},
            )

        if not matches:
            msg = f"No files matched pattern '{pattern}'" + (
                f" with content regex '{content_regex}'" if content_regex else ""
            )
            return ToolResult(
                output=msg,
                success=True,
                metadata={"count": 0},
            )

        return ToolResult(
            output=f"Found {len(matches)} file(s):\n" + "\n".join(matches),
            success=True,
            metadata={"count": len(matches), "matches": matches},
        )
