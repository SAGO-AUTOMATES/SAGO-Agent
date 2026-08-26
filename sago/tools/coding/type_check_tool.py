"""Type Check Tool - Run type checking and diagnostics on code."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.type_check_tool")


class TypeCheckArgs(BaseModel):
    """Arguments for TypeCheckTool."""

    file_path: str = Field(description="Path to the file to check")
    action: str = Field(default="check", description="Action: check, format, completions")


class TypeCheckTool(BaseTool):
    """Tool for type checking code using language servers."""

    name = "type_check"
    description = (
        "Run type checking on code files. Detects errors, warnings, "
        "and can format code or get completions."
    )
    args_model = TypeCheckArgs

    def _run(
        self,
        file_path: str,
        action: str = "check",
        **kwargs: Any,
    ) -> str:
        """Run type check action."""
        from sago.tools.coding.lsp_client import get_lsp_client

        client = get_lsp_client()

        if action == "check":
            diagnostics = client.check_types(file_path)
            if not diagnostics:
                return f"No type errors found in {file_path}"

            lines = [f"=== Type Check Results: {file_path} ==="]
            errors = [d for d in diagnostics if d.severity == "error"]
            warnings = [d for d in diagnostics if d.severity == "warning"]

            if errors:
                lines.append(f"\nErrors ({len(errors)}):")
                for d in errors:
                    lines.append(f"  {d}")

            if warnings:
                lines.append(f"\nWarnings ({len(warnings)}):")
                for d in warnings:
                    lines.append(f"  {d}")

            return "\n".join(lines)

        elif action == "format":
            formatted = client.format_code(file_path)
            if formatted:
                return f"Formatted {file_path}"
            return f"Could not format {file_path} (formatter not available)"

        elif action == "completions":
            completions = client.get_completions(file_path, 1, 0)
            if not completions:
                return f"No completions available for {file_path}"
            lines = [f"Completions for {file_path}:"]
            for c in completions[:20]:
                lines.append(f"  {c.label} ({c.kind})")
            return "\n".join(lines)

        else:
            return f"Unknown action: {action}. Use: check, format, completions"
