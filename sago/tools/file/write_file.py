"""Write File Tool - Write content to a file.

Creates or overwrites files with optional backup, syntax validation, and smart encoding.
"""

from __future__ import annotations

import ast
import shutil
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.errors import log_error


class WriteFileArgs(BaseModel):
    """Arguments for WriteFileTool."""

    file_path: str = Field(description="Path to the file to write")
    content: str = Field(description="Content to write to the file")
    encoding: str = Field(default="utf-8", description="File encoding (default: utf-8)")
    create_dirs: bool = Field(
        default=True, description="Create parent directories if they don't exist"
    )
    backup: bool = Field(default=False, description="Create a backup before writing")


class WriteFileTool(BaseTool):
    """Tool for writing file contents."""

    name = "write_file"
    description = (
        "Write content to a file. Creates the file if it doesn't exist, overwrites if it does."
    )
    args_model = WriteFileArgs

    def _run(
        self,
        file_path: str,
        content: str,
        encoding: str = "utf-8",
        create_dirs: bool = True,
        backup: bool = False,
        **kwargs: Any,
    ) -> str:
        """Write content to a file.

        Args:
            file_path: Path to the file to write.
            content: Content to write.
            encoding: File encoding.
            create_dirs: Whether to create parent directories.
            backup: Whether to backup existing file first.

        Returns:
            Success or error message.
        """
        path = self._expand_path(file_path)

        # Create parent directories if needed
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)

        try:
            # Track the change
            try:
                from sago.memory.change_tracker import get_change_tracker

                tracker = get_change_tracker()
                old_content = path.read_text(encoding=encoding) if path.exists() else None
                if old_content is not None:
                    tracker.track_modify(str(path), old_content, content)
                else:
                    tracker.track_create(str(path), content)
            except Exception as e:
                log_error("Failed to track write change", e, context={"path": str(path)})

            path.write_text(content, encoding=encoding)
            size = len(content)
            lines = len(content.splitlines())
            msg = f"Successfully wrote {size} bytes ({lines} lines) to {path}"

            # Smart: syntax validation after write for known languages
            ext = path.suffix.lower()
            if ext == ".py":
                try:
                    ast.parse(content, filename=str(path))
                    msg += " [syntax: OK]"
                except SyntaxError as e:
                    msg += f" [syntax: ERROR at line {e.lineno}: {e.msg}]"
            elif ext in (".json",):
                try:
                    import json

                    json.loads(content)
                    msg += " [json: OK]"
                except Exception as e:
                    msg += f" [json: ERROR {e}]"
            elif ext in (".yaml", ".yml"):
                try:
                    import yaml  # type: ignore

                    yaml.safe_load(content)
                    msg += " [yaml: OK]"
                except Exception:
                    pass  # yaml not required
            return msg
        except Exception as e:
            return f"Error writing file: {e}"
