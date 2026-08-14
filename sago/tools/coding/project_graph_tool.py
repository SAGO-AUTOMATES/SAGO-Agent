"""Project Graph Tool - Builds complete data, process, and architecture diagrams."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.memory.project_graph import ProjectGraph
from sago.tools.base import BaseTool


class ProjectGraphArgs(BaseModel):
    """Arguments for ProjectGraphTool."""

    directory: str = Field(default=".", description="Root directory to analyze")
    view: str = Field(
        default="dashboard",
        description="View type: 'dashboard' (full curated suite), 'arch' (layered box diagram), 'process' (pipeline map), 'tree' (file dependency tree), 'mermaid' (visual flowchart), 'llm' (compact summary), or 'json'",
    )
    focus: str | None = Field(
        default=None, description="Optional focus filter (e.g. 'database', 'auth', or file name)"
    )
    max_files: int = Field(default=400, description="Max files to analyze")


class ProjectGraphTool(BaseTool):
    """Tool for analyzing complete project architecture, inter-module dependencies, and data models."""

    name = "project_graph"
    description = (
        "Generate a deep architecture diagram, execution process map, file dependency graph, "
        "and data models in curated dashboard, ASCII, Mermaid, or JSON."
    )
    args_model = ProjectGraphArgs
    risk_level = "safe"

    def _run(
        self,
        directory: str = ".",
        view: str = "dashboard",
        focus: str | None = None,
        max_files: int = 400,
        **kwargs: Any,
    ) -> str:
        target_dir = self._expand_path(directory)
        if not target_dir.exists() or not target_dir.is_dir():
            return f"Error: Directory not found: {target_dir}"

        graph = ProjectGraph(root_dir=target_dir)
        graph.build_graph(max_files=max_files)

        v = view.lower().strip()
        if v in ("arch", "architecture"):
            return graph.to_architecture_diagram()
        elif v in ("process", "pipeline"):
            return graph.to_process_map()
        elif v in ("tree", "ascii"):
            return graph.to_ascii_tree()
        elif v == "mermaid":
            return graph.to_mermaid(focus_filter=focus)
        elif v == "json":
            import json

            return json.dumps(graph.to_dict(), indent=2)
        elif v == "llm":
            return graph.to_llm_context()
        else:
            return graph.to_curated_dashboard(focus_filter=focus)
