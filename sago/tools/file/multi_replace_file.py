"""Multi Replace Tool - Make multiple non-contiguous edits to a single file atomically."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.tools.file.resilient_editor import ResilientEditor
from sago.utils.errors import log_error


class ReplacementChunk(BaseModel):
    """A single replacement chunk."""

    old_string: str = Field(description="Target string/block to find and replace")
    new_string: str = Field(description="Replacement string")


class MultiReplaceArgs(BaseModel):
    """Arguments for MultiReplaceTool."""

    file_path: str = Field(description="Path to the file to edit")
    chunks: list[dict[str, str]] = Field(
        description="List of replacement chunks, each with 'old_string' (or 'old') and 'new_string' (or 'new')"
    )
    encoding: str = Field(default="utf-8", description="File encoding")


class MultiReplaceTool(BaseTool):
    """Tool for applying multiple non-contiguous edits to a file atomically."""

    name = "multi_replace_file"
    description = (
        "Apply multiple non-contiguous replacements to a single file in one atomic operation."
    )
    args_model = MultiReplaceArgs

    def _run(
        self,
        file_path: str = "",
        chunks: list[dict[str, str]] | None = None,
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> str:
        if not file_path:
            return "Error: file_path is required"
        if not chunks:
            return "Error: chunks list is required"
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = path.read_text(encoding=encoding)
        except Exception as e:
            return f"Error reading file: {e}"

        # Standardize keys
        standardized_chunks = []
        for c in chunks:
            old_s = c.get("old_string") or c.get("old") or ""
            new_s = c.get("new_string") or c.get("new") or ""
            standardized_chunks.append({"old": old_s, "new": new_s})

        success, new_content, logs, total_replaced = ResilientEditor.apply_multi_replace(
            content=content, chunks=standardized_chunks
        )

        if not success:
            return f"Error applying multi-replace on {path}:\n" + "\n".join(logs)

        try:
            try:
                from sago.memory.change_tracker import get_change_tracker

                tracker = get_change_tracker()
                tracker.track_modify(str(path), content, new_content)
            except Exception as e:
                log_error("Failed to track multi-replace change", e, context={"path": str(path)})

            path.write_text(new_content, encoding=encoding)
            return f"Successfully applied {total_replaced} replacement(s) to {path}:\n" + "\n".join(
                logs
            )
        except Exception as e:
            return f"Error writing updated file: {e}"
