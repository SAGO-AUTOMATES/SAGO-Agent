"""LSP Query Tool - Diagnostics and go-to-definition via language servers/CLI fallbacks."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.lsp_query_tool")


class LSPQueryArgs(BaseModel):
    action: str = Field(default="diagnostics", description="diagnostics | definitions | hover")
    file_path: str = Field(description="File to query")
    line: int = Field(default=1, description="1-based line number")
    column: int = Field(default=1, description="1-based column number")


class LSPQueryTool(BaseTool):
    name = "lsp_query"
    description = (
        "PREFER for type/definition info: run LSP diagnostics or go-to-definition "
        "(falls back to CLI tools when servers unavailable)."
    )
    args_model = LSPQueryArgs

    def _run(
        self,
        action: str = "diagnostics",
        file_path: str = "",
        line: int = 1,
        column: int = 1,
        **kwargs: Any,
    ) -> str:
        from sago.tools.coding.lsp_client import get_lsp_client

        client = get_lsp_client()
        path = self._expand_path(file_path)
        if not path.exists():
            return f"Error: File not found: {path}"

        action = (action or "diagnostics").lower()
        if action == "diagnostics":
            diags = client.get_diagnostics(str(path))
            if not diags:
                return f"No diagnostics for {path}"
            return "\n".join(str(d) for d in diags)
        if action == "definitions":
            defs = client.get_definitions(str(path), line=line, column=column)
            if not defs:
                return f"No definitions found at {path}:{line}:{column}"
            return "\n".join(f"{d.file}:{d.line}:{d.column}" for d in defs)
        if action == "hover":
            info = client.get_hover(str(path), line=line, column=column)
            if not info:
                return f"No hover info at {path}:{line}:{column}"
            return str(info)
        return f"Unknown action: {action}"
