"""Write File Tool - Write content to a file.

Creates or overwrites files with optional backup, syntax validation, and smart encoding.
"""

from __future__ import annotations

import ast
import logging
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tools.file.write_file")


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

        # Write safety check for sensitive and system paths
        from sago.security.approval import check_write_safety

        blocked_reason = check_write_safety(path)
        if blocked_reason:
            logger.warning("Write safety rejected path '%s': %s", path, blocked_reason)
            return f"Error: {blocked_reason}"

        # Create parent directories if needed
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)

        # Pre-write syntax validation for structured file formats
        ext = path.suffix.lower()
        if ext == ".json":
            try:
                import json

                json.loads(content)
            except Exception as e:
                return f"Error: Pre-write validation failed for JSON file: {e}"
        elif ext in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore

                yaml.safe_load(content)
            except Exception as e:
                return f"Error: Pre-write validation failed for YAML file: {e}"

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

            # Atomic write: write to temporary file in same directory then rename
            import hashlib
            import os
            import tempfile

            temp_fd, temp_path_str = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_sago_")
            temp_path = Path(temp_path_str)
            try:
                with os.fdopen(temp_fd, "w", encoding=encoding) as f:
                    f.write(content)

                if path.exists():
                    try:
                        st = path.stat()
                        os.chmod(temp_path, st.st_mode)
                    except Exception:
                        pass

                temp_path.replace(path)

                # Post-write SHA-256 integrity verification
                written_hash = hashlib.sha256(
                    content.encode(encoding, errors="replace")
                ).hexdigest()
                disk_hash = hashlib.sha256(path.read_bytes()).hexdigest()
                if written_hash != disk_hash:
                    return f"Error: Post-write integrity verification mismatch for {path}"
            except Exception as e:
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                    except Exception:
                        pass
                raise e

            size = len(content)
            lines = len(content.splitlines())
            msg = f"Successfully wrote {size} bytes ({lines} lines) to {path}"

            # Smart: syntax validation after write for known languages
            if ext == ".py":
                try:
                    ast.parse(content, filename=str(path))
                    msg += " [syntax: OK]"
                except SyntaxError as e:
                    msg += f" [syntax: ERROR at line {e.lineno}: {e.msg}]"
            elif ext in (".json",):
                msg += " [json: OK]"
            elif ext in (".yaml", ".yml"):
                msg += " [yaml: OK]"
            return msg
        except Exception as e:
            return f"Error writing file: {e}"
