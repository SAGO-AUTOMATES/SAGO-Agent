"""Edit File Tool - Edit files using exact string replacement.

Safely edit files with precise string matching and replacement.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class EditFileArgs(BaseModel):
    """Arguments for EditFileTool."""

    file_path: str = Field(description="Path to the file to edit")
    old_string: str = Field(description="Exact string to find and replace")
    new_string: str = Field(description="String to replace with")
    encoding: str = Field(default="utf-8", description="File encoding")
    replace_all: bool = Field(
        default=False, description="Replace all occurrences (default: first only)"
    )


class EditFileTool(BaseTool):
    """Tool for editing files using exact string replacement."""

    name = "edit_file"
    description = "Edit a file by finding an exact string and replacing it with new content."
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
        """Edit a file using string replacement.

        Args:
            file_path: Path to the file.
            old_string: String to find.
            new_string: Replacement string.
            encoding: File encoding.
            replace_all: Replace all occurrences.

        Returns:
            Success or error message.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = path.read_text(encoding=encoding)
        except Exception as e:
            return f"Error reading file: {e}"

        if old_string not in content:
            return f"Error: String not found in {path}:\n'{old_string[:100]}...'"

        try:
            # Track the change
            try:
                from sago.memory.change_tracker import get_change_tracker

                tracker = get_change_tracker()
                if replace_all:
                    new_content = content.replace(old_string, new_string)
                else:
                    new_content = content.replace(old_string, new_string, 1)
                tracker.track_modify(str(path), content, new_content)
            except Exception:
                pass

            if replace_all:
                count = content.count(old_string)
                content = content.replace(old_string, new_string)
                path.write_text(content, encoding=encoding)
                return f"Replaced {count} occurrence(s) in {path}"
            else:
                content = content.replace(old_string, new_string, 1)
                path.write_text(content, encoding=encoding)
                return f"Successfully edited {path}"
        except Exception as e:
            return f"Error editing file: {e}"
