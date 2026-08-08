"""Permission Manager Tool - Manage file and directory permissions.

Cross-platform permission management.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class PermissionManagerArgs(BaseModel):
    """Arguments for PermissionManagerTool."""

    operation: Literal["check", "chmod", "chown", "info"] = Field(description="Permission operation")
    path: str = Field(description="File or directory path")
    mode: str | None = Field(default=None, description="Permission mode (e.g., '755', 'u+x')")
    owner: str | None = Field(default=None, description="New owner (for chown)")


class PermissionManagerTool(BaseTool):
    """Tool for managing file and directory permissions."""

    name = "permission_manager"
    description = "View and modify file/directory permissions across platforms."
    args_model = PermissionManagerArgs

    def _run(
        self,
        operation: str,
        path: str,
        mode: str | None = None,
        owner: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Manage file permissions.

        Args:
            operation: Permission operation.
            path: Target path.
            mode: Permission mode.
            owner: New owner.

        Returns:
            Operation result.
        """
        target = self._expand_path(path)

        if not target.exists():
            return f"Error: Path not found: {target}"

        if operation == "check":
            return self._check_permissions(target)
        elif operation == "info":
            return self._get_info(target)
        elif operation == "chmod":
            if mode is None:
                return "Error: mode required for chmod"
            return self._chmod(target, mode)
        elif operation == "chown":
            if owner is None:
                return "Error: owner required for chown"
            return self._chown(target, owner)

        return f"Error: Unknown operation: {operation}"

    def _check_permissions(self, path: Path) -> str:
        """Check file permissions."""
        import os
        import stat

        st = os.stat(path)
        mode = stat.S_IMODE(st.st_mode)

        perms = []
        if mode & stat.S_IRUSR:
            perms.append("r")
        if mode & stat.S_IWUSR:
            perms.append("w")
        if mode & stat.S_IXUSR:
            perms.append("x")

        perm_str = "".join(perms) if perms else "---"

        return (
            f"File: {path}\n"
            f"Permissions: {oct(mode)} ({perm_str})\n"
            f"Readable: {os.access(path, os.R_OK)}\n"
            f"Writable: {os.access(path, os.W_OK)}\n"
            f"Executable: {os.access(path, os.X_OK)}"
        )

    def _get_info(self, path: Path) -> str:
        """Get detailed file info."""
        import os
        import stat

        st = os.stat(path)

        return (
            f"Path: {path}\n"
            f"Mode: {oct(st.st_mode)}\n"
            f"UID: {st.st_uid}\n"
            f"GID: {st.st_gid}\n"
            f"Size: {st.st_size} bytes\n"
            f"Is directory: {path.is_dir()}"
        )

    def _chmod(self, path: Path, mode: str) -> str:
        """Change file permissions."""
        import os

        try:
            # Try numeric mode
            if mode.isdigit():
                os.chmod(path, int(mode, 8))
                return f"Set permissions on {path} to {mode}"
            else:
                # Use chmod command for symbolic modes
                result = self._run_command(f"chmod {mode} {path}")
                if result.returncode == 0:
                    return f"Set permissions on {path} to {mode}"
                return f"Error: {result.stderr}"
        except Exception as e:
            return f"Error changing permissions: {e}"

    def _chown(self, path: Path, owner: str) -> str:
        """Change file owner."""
        result = self._run_command(f"chown {owner} {path}")
        if result.returncode == 0:
            return f"Changed owner of {path} to {owner}"
        return f"Error: {result.stderr}"
