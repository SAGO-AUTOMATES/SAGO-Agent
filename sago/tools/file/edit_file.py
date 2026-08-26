"""Edit File Tool - Resilient intelligent string and block replacement.

Safely edit files with multi-tier exact, normalized, and fuzzy matching.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.tools.file.resilient_editor import ResilientEditor
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tools.file.edit_file")


class EditFileArgs(BaseModel):
    """Arguments for EditFileTool."""

    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="Exact or target string to find and replace")
    new_string: str = Field(description="String to replace with")
    encoding: str = Field(default="utf-8", description="File encoding")
    replace_all: bool = Field(
        default=False, description="Replace all occurrences (default: first only)"
    )


class EditFileTool(BaseTool):
    """Tool for editing files using resilient multi-tier replacement."""

    name = "edit_file"
    description = "Edit a file by finding a target string/block and replacing it with new content (supports exact and resilient matching)."
    args_model = EditFileArgs

    def _run(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        encoding: str = "utf-8",
        replace_all: bool = False,
        **kwargs: Any,
    ) -> str:
        """Edit a file using resilient replacement."""
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = path.read_text(encoding=encoding)
        except Exception as e:
            return f"Error reading file: {e}"

        success, new_content, log_msg = ResilientEditor.apply_replacement(
            content=content,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            path=str(path),
        )

        if not success:
            preview = old_string[:120] + ("..." if len(old_string) > 120 else "")
            if "REJECTED" in log_msg:
                return f"Error: {log_msg}"
            return f"Error: String not found in {path}:\n'{preview}'\nDetail: {log_msg}"

        try:
            # Track the change
            try:
                from sago.memory.change_tracker import get_change_tracker

                tracker = get_change_tracker()
                tracker.track_modify(str(path), content, new_content)
            except Exception as e:
                log_error("Failed to track edit change", e, context={"path": str(path)})

            path.write_text(new_content, encoding=encoding)
            return f"Successfully edited {path} ({log_msg})"
        except Exception as e:
            return f"Error editing file: {e}"
