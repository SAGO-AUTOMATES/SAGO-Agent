"""Repo Map Tool - Generates compact symbol outlines across massive repositories."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.memory.symbol_graph import SymbolGraph
from sago.tools.base import BaseTool


class RepoMapArgs(BaseModel):
    """Arguments for RepoMapTool."""

    directory: str = Field(default=".", description="Root directory to map")
    filter_query: str | None = Field(
        default=None, description="Optional filter for specific file path or symbol name"
    )
    max_files: int = Field(default=200, description="Max files to include in map")


class RepoMapTool(BaseTool):
    """Tool for inspecting the high-level architecture and symbols of the codebase."""

    name = "repo_map"
    description = "Generate a compact symbol map (classes, methods, functions, line counts) across the repository."
    args_model = RepoMapArgs

    def _run(
        self,
        directory: str = ".",
        filter_query: str | None = None,
        max_files: int = 200,
        **kwargs: Any,
    ) -> str:
        target_dir = self._expand_path(directory)
        if not target_dir.exists() or not target_dir.is_dir():
            return f"Error: Directory not found: {target_dir}"

        graph = SymbolGraph(root_dir=target_dir)
        repo_map = graph.generate_repo_map(
            max_files=max_files,
            filter_query=filter_query,
        )

        if not repo_map.strip():
            return "No matching source files or symbols found."

        return f"=== REPOSITORY SYMBOL MAP ({target_dir.name}/) ===\n\n{repo_map}"
