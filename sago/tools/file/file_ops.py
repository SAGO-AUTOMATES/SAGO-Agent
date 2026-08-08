"""File Operations Tool - Move, copy, delete, rename files.

Cross-platform file operations with safety checks.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class FileOperationsArgs(BaseModel):
    """Arguments for FileOperationsTool."""

    operation: Literal["move", "copy", "delete", "rename", "mkdir", "list"] = Field(description="Operation to perform")
    source: str = Field(description="Source file or directory path")
    destination: str | None = Field(default=None, description="Destination path (for move/copy/rename)")
    recursive: bool = Field(default=False, description="Operate recursively on directories")
    force: bool = Field(default=False, description="Force overwrite existing files")


class FileOperationsTool(BaseTool):
    """Tool for file system operations (move, copy, delete, rename, mkdir, list)."""

    name = "file_operations"
    description = "Perform file operations: move, copy, delete, rename, mkdir, or list directory contents."
    args_model = FileOperationsArgs

    def _run(
        self,
        operation: str,
        source: str,
        destination: str | None = None,
        recursive: bool = False,
        force: bool = False,
        **kwargs: Any,
    ) -> str:
        """Execute a file operation.

        Args:
            operation: Operation type (move, copy, delete, rename, mkdir, list).
            source: Source path.
            destination: Destination path.
            recursive: Recursive operation.
            force: Force overwrite.

        Returns:
            Result message.
        """
        src = self._expand_path(source)

        if operation == "list":
            return self._list_directory(src)

        if operation == "mkdir":
            src.mkdir(parents=True, exist_ok=True)
            return f"Created directory: {src}"

        if operation == "delete":
            return self._delete_path(src, recursive, force)

        if destination is None:
            return f"Error: Destination required for {operation}"

        dst = self._expand_path(destination)

        if operation == "move":
            return self._move_path(src, dst, force)
        elif operation == "copy":
            return self._copy_path(src, dst, recursive, force)
        elif operation == "rename":
            return self._move_path(src, dst, force)

        return f"Error: Unknown operation: {operation}"

    def _list_directory(self, path: Path) -> str:
        """List directory contents."""
        if not path.exists():
            return f"Error: Directory not found: {path}"
        if not path.is_dir():
            return f"Error: Not a directory: {path}"

        entries = sorted(path.iterdir())
        lines = [f"Contents of {path}:\n"]
        for entry in entries:
            if entry.is_dir():
                lines.append(f"  [DIR]  {entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"  [FILE] {entry.name} ({size} bytes)")

        return "\n".join(lines)

    def _delete_path(self, path: Path, recursive: bool, force: bool) -> str:
        """Delete a file or directory."""
        if not path.exists():
            return f"Error: Path not found: {path}"

        if path.is_dir():
            if not recursive:
                return f"Error: {path} is a directory. Use recursive=true to delete."
            shutil.rmtree(path)
            return f"Deleted directory: {path}"
        else:
            path.unlink()
            return f"Deleted file: {path}"

    def _move_path(self, src: Path, dst: Path, force: bool) -> str:
        """Move a file or directory."""
        if not src.exists():
            return f"Error: Source not found: {src}"
        if dst.exists() and not force:
            return f"Error: Destination exists: {dst}. Use force=true to overwrite."

        shutil.move(str(src), str(dst))
        return f"Moved {src} -> {dst}"

    def _copy_path(self, src: Path, dst: Path, recursive: bool, force: bool) -> str:
        """Copy a file or directory."""
        if not src.exists():
            return f"Error: Source not found: {src}"
        if dst.exists() and not force:
            return f"Error: Destination exists: {dst}. Use force=true to overwrite."

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

        return f"Copied {src} -> {dst}"
