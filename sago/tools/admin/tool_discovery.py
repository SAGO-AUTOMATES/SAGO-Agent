"""Tool Discovery Tool - List dynamically discovered tools (with safe mode flag)."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.tools.registry import discover_tools

logger = logging.getLogger("sago.tools.admin.tool_discovery")


class ToolDiscoveryArgs(BaseModel):
    category: str | None = Field(default=None, description="Filter by category")
    query: str | None = Field(default=None, description="Search query")
    safe_mode: bool = Field(default=False, description="Exclude plugins and MCP tools")


class ToolDiscoveryTool(BaseTool):
    name = "discover_tools"
    description = "List dynamically discovered tools; safe_mode excludes plugins/MCP."
    args_model = ToolDiscoveryArgs

    def _run(self, category=None, query=None, safe_mode=False, **kwargs: Any) -> str:
        tools = discover_tools(safe_mode=safe_mode)
        results = list(tools.values())
        if category:
            results = [t for t in results if t.category.lower() == category.lower()]
        if query:
            q = query.lower()
            results = [t for t in results if q in t.name.lower() or q in t.description.lower()]
        lines = [
            f"{t.name} ({t.category}) - {t.description[:80]}"
            for t in sorted(results, key=lambda x: x.name)
        ]
        return f"Discovered {len(lines)} tools:\n" + "\n".join(lines)
