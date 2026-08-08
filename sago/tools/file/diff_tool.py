"""Diff Tool - Compare files and text."""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DiffArgs(BaseModel):
    """Arguments for diff operations."""

    operation: str = Field(description="Operation: files, text, unified, context")
    source: str = Field(description="First file path or text")
    target: str = Field(description="Second file path or text")
    context_lines: int = Field(default=3, description="Context lines for unified diff")


class DiffTool(BaseTool):
    """Tool for comparing files and text."""

    name: str = "diff_tool"
    description: str = (
        "Compare files and text: unified diff, context diff, side-by-side."
    )
    args_model: type[BaseModel] = DiffArgs

    def _run(
        self,
        operation: str,
        source: str,
        target: str,
        context_lines: int = 3,
        **kwargs: Any,
    ) -> str:
        """Execute diff operation."""
        try:
            # Determine if inputs are files or text
            source_path = self._expand_path(source)
            target_path = self._expand_path(target)

            if source_path.exists() and source_path.is_file():
                source_lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                source_label = str(source_path)
            else:
                source_lines = source.splitlines(keepends=True)
                source_label = "<source text>"

            if target_path.exists() and target_path.is_file():
                target_lines = target_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                target_label = str(target_path)
            else:
                target_lines = target.splitlines(keepends=True)
                target_label = "<target text>"

            if operation == "unified":
                diff = difflib.unified_diff(
                    source_lines,
                    target_lines,
                    fromfile=source_label,
                    tofile=target_label,
                    n=context_lines,
                )
                result = "".join(diff)
                return result if result else "No differences found"

            elif operation == "context":
                diff = difflib.context_diff(
                    source_lines,
                    target_lines,
                    fromfile=source_label,
                    tofile=target_label,
                    n=context_lines,
                )
                result = "".join(diff)
                return result if result else "No differences found"

            elif operation == "text":
                # Compare as plain text
                matcher = difflib.SequenceMatcher(None, source_lines, target_lines)
                opcodes = matcher.get_opcodes()

                result_parts = []
                for tag, i1, i2, j1, j2 in opcodes:
                    if tag == "equal":
                        continue
                    elif tag == "replace":
                        result_parts.append(f"--- Change at line {i1+1}-{i2} ---")
                        result_parts.append("".join(source_lines[i1:i2]))
                        result_parts.append(f"+++ Changed to: +++")
                        result_parts.append("".join(target_lines[j1:j2]))
                    elif tag == "delete":
                        result_parts.append(f"--- Deleted at line {i1+1}-{i2} ---")
                        result_parts.append("".join(source_lines[i1:i2]))
                    elif tag == "insert":
                        result_parts.append(f"+++ Inserted at line {i1+1} +++")
                        result_parts.append("".join(target_lines[j1:j2]))

                return "\n".join(result_parts) if result_parts else "No differences found"

            elif operation == "files":
                # Get file stats
                matcher = difflib.SequenceMatcher(None, source_lines, target_lines)
                ratio = matcher.ratio()

                result_parts = [
                    f"Comparing: {source_label} vs {target_label}",
                    f"Similarity: {ratio*100:.1f}%",
                    f"Source lines: {len(source_lines)}",
                    f"Target lines: {len(target_lines)}",
                    "",
                ]

                # Show differences
                opcodes = matcher.get_opcodes()
                changes = sum(1 for tag, *_ in opcodes if tag != "equal")
                result_parts.append(f"Changes: {changes}")

                # Show first few differences
                for tag, i1, i2, j1, j2 in opcodes[:5]:
                    if tag != "equal":
                        result_parts.append(f"  {tag}: source[{i1}:{i2}] -> target[{j1}:{j2}]")

                return "\n".join(result_parts)

            else:
                return f"Error: Invalid operation '{operation}'. Valid: files, text, unified, context"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"


def get_tool() -> type[DiffTool]:
    """Get the tool class."""
    return DiffTool
