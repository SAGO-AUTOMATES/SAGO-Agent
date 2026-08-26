"""Environment Manager Tool - Manage environment variables and paths.

Cross-platform environment variable management.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.system.env_manager")


class EnvManagerArgs(BaseModel):
    """Arguments for EnvManagerTool."""

    operation: Literal["get", "set", "list", "path", "load", "save"] = Field(
        description="Operation to perform"
    )
    key: str | None = Field(default=None, description="Environment variable name")
    value: str | None = Field(default=None, description="Value to set")
    file_path: str | None = Field(default=None, description="Env file path for load/save")


class EnvManagerTool(BaseTool):
    """Tool for managing environment variables and system paths."""

    name = "env_manager"
    description = "Get, set, and manage environment variables and system paths."
    args_model = EnvManagerArgs

    def _run(
        self,
        operation: str,
        key: str | None = None,
        value: str | None = None,
        file_path: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Perform an environment operation.

        Args:
            operation: Operation type.
            key: Variable name.
            value: Variable value.
            file_path: Env file path.

        Returns:
            Operation result.
        """
        logger.debug(
            "env_manager called: operation=%s, key=%s, file_path=%s", operation, key, file_path
        )

        if operation == "get":
            if key is None:
                return "Error: key required for get"
            value = os.environ.get(key)
            logger.debug("Env get: key=%s, found=%s", key, value is not None)
            return value if value is not None else f"Variable '{key}' not set"

        elif operation == "set":
            if key is None or value is None:
                return "Error: key and value required for set"
            os.environ[key] = value
            logger.info("Env set: key=%s, value_len=%d", key, len(value))
            return f"Set {key}={value}"

        elif operation == "list":
            logger.info("Listing all environment variables")
            return self._list_env()

        elif operation == "path":
            logger.info("Listing PATH entries")
            return self._list_path()

        elif operation == "load":
            if file_path is None:
                return "Error: file_path required for load"
            logger.info("Loading env file: %s", file_path)
            return self._load_env_file(file_path)

        elif operation == "save":
            if file_path is None:
                return "Error: file_path required for save"
            logger.info("Saving env file: %s", file_path)
            return self._save_env_file(file_path)

        logger.warning("Unknown env_manager operation: %s", operation)
        return f"Error: Unknown operation: {operation}"

    def _list_env(self) -> str:
        """List all environment variables."""
        lines = [f"=== Environment Variables ({len(os.environ)}) ==="]
        for key, value in sorted(os.environ.items()):
            display_value = value if len(value) < 100 else value[:100] + "..."
            lines.append(f"  {key}={display_value}")
        return "\n".join(lines)

    def _list_path(self) -> str:
        """List PATH entries."""
        path_str = os.environ.get("PATH", "")
        paths = path_str.split(os.pathsep)
        lines = [f"=== PATH ({len(paths)} entries) ==="]
        for p in paths:
            exists = "OK" if Path(p).exists() else "MISSING"
            lines.append(f"  [{exists}] {p}")
        return "\n".join(lines)

    def _load_env_file(self, file_path: str) -> str:
        """Load environment variables from a file."""
        path = self._expand_path(file_path)

        if not path.exists():
            logger.warning("Env file not found: %s", path)
            return f"Error: File not found: {path}"

        try:
            content = path.read_text(encoding="utf-8")
            loaded = 0

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    os.environ[key] = val
                    loaded += 1

            logger.info("Loaded %d env vars from %s", loaded, path)
            return f"Loaded {loaded} variables from {path}"

        except Exception as e:
            logger.error("Failed to load env file: path=%s, error=%s", path, e)
            return f"Error loading env file: {e}"

    def _save_env_file(self, file_path: str) -> str:
        """Save environment variables to a file."""
        path = self._expand_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            lines = ["# Environment variables exported by Sago\n"]
            for key, value in sorted(os.environ.items()):
                if key.startswith("_"):
                    continue
                lines.append(f'{key}="{value}"')

            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info("Saved %d env vars to %s", len(os.environ), path)
            return f"Saved {len(os.environ)} variables to {path}"

        except Exception as e:
            logger.error("Failed to save env file: path=%s, error=%s", path, e)
            return f"Error saving env file: {e}"
