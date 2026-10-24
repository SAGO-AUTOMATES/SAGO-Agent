"""Read Function Tool - Extract a specific function/class by name without reading the whole file."""

from __future__ import annotations

import ast
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.read_function_tool")


class ReadFunctionArgs(BaseModel):
    file_path: str = Field(description="Path to the file")
    name: str = Field(description="Function or class name to extract")
    include_context: bool = Field(
        default=True, description="Include preceding decorators/imports header"
    )


class ReadFunctionTool(BaseTool):
    name = "read_function"
    description = (
        "PREFER for targeted reads: extract a specific function or class by name "
        "from a file without reading the whole file."
    )
    args_model = ReadFunctionArgs

    def _run(self, file_path: str, name: str, include_context: bool = True, **kwargs: Any) -> str:
        path = self._expand_path(file_path)
        if not path.exists() or not path.is_file():
            return f"Error: File not found: {path}"
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

        lines = content.splitlines(keepends=True)

        # Python: use AST
        if path.suffix.lower() == ".py":
            try:
                tree = ast.parse(content)
            except SyntaxError as e:
                return f"SyntaxError: {e}"
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    and node.name == name
                ):
                    start = node.lineno - 1
                    end = getattr(node, "end_lineno", node.lineno) or node.lineno
                    snippet = "".join(lines[start:end])
                    return f"--- {path}: {name} (lines {start + 1}-{end}) ---\n{snippet}"
            return f"Symbol '{name}' not found in {path}"

        # Generic: regex header + brace/indent block
        # Find a line defining the symbol
        patterns = [
            rf"^\s*(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\b",
            rf"^\s*(?:export\s+)?class\s+{re.escape(name)}\b",
            rf"^\s*(?:pub\s+)?(?:async\s+)?fn\s+{re.escape(name)}\b",
            rf"^\s*def\s+{re.escape(name)}\b",
            rf"^\s*func\s+(?:\(.*?\)\s+)?{re.escape(name)}\b",
        ]
        for i, line in enumerate(lines):
            if any(re.search(p, line) for p in patterns):
                # brace-aware end
                try:
                    from sago.utils.code_blocks import brace_block_spans

                    if "{" in "".join(lines[i : i + 3]):
                        bi = i
                        while bi < len(lines) and "{" not in lines[bi]:
                            bi += 1
                        s, e = brace_block_spans(lines, bi)
                        # include header lines before brace
                        start = i
                        end = e
                    else:
                        # indent-based (Python-like) fallback
                        start = i
                        base_indent = len(lines[i]) - len(lines[i].lstrip())
                        end = i + 1
                        while end < len(lines) and (
                            lines[end].strip() == ""
                            or (len(lines[end]) - len(lines[end].lstrip())) > base_indent
                        ):
                            end += 1
                except Exception:
                    start = i
                    end = min(i + 40, len(lines))
                snippet = "".join(lines[start:end])
                return f"--- {path}: {name} (lines {start + 1}-{end}) ---\n{snippet}"
        return f"Symbol '{name}' not found in {path}"
