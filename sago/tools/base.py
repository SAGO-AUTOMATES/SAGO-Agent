"""Base tool class for all Sago tools.

All tools inherit from BaseTool and implement the _run method.
Tools are designed to be cross-platform (Windows, Mac, Linux).
"""

from __future__ import annotations

import os
import platform
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class BaseTool(ABC):
    """Abstract base class for all Sago tools.

    Each tool must:
    - Have a unique name
    - Implement _run() with the actual logic
    - Use the ArgsModel for typed arguments
    """

    name: str = ""
    description: str = ""
    args_model: type[BaseModel] | None = None

    def __init__(self) -> None:
        """Initialize the tool."""
        self._os_type = platform.system().lower()

    @abstractmethod
    def _run(self, **kwargs: Any) -> str:
        """Execute the tool with the given arguments.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            String result of the tool execution.
        """
        ...

    def run(self, **kwargs: Any) -> str:
        """Run the tool with validation, error handling, and recovery.

        Permission checks are handled by the executor layer (TUI, simple_executor, unified).
        This method does NOT check permissions to avoid conflicts with YOLO mode.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            String result of the tool execution.
        """
        try:
            return self._run(**kwargs)
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"

            # Try to find a known fix from learning store
            try:
                from sago.learning import get_learning_store

                ls = get_learning_store()
                known_fix = ls.get_known_fixes(error_msg)
                if known_fix:
                    return f"Error in {self.name}: {error_msg}\nKnown fix: {known_fix}"
            except Exception:
                pass

            # Record this error for future learning
            try:
                from sago.learning import get_learning_store

                ls = get_learning_store()
                ls.record_failure("tool_error", error_msg, f"Tool: {self.name}")
            except Exception:
                pass

            return f"Error in {self.name}: {error_msg}"

    def _is_windows(self) -> bool:
        """Check if running on Windows."""
        return self._os_type == "windows"

    def _is_macos(self) -> bool:
        """Check if running on macOS."""
        return self._os_type == "darwin"

    def _is_linux(self) -> bool:
        """Check if running on Linux."""
        return self._os_type == "linux"

    def _get_shell(self) -> str:
        """Get the appropriate shell for the current OS."""
        if self._is_windows():
            return "powershell"
        return os.environ.get("SHELL", "/bin/bash")

    def _run_command(
        self,
        command: str | list[str],
        timeout: int = 300,
        cwd: str | Path | None = None,
        shell: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a system command cross-platform.

        Args:
            command: Command string or list of arguments.
            timeout: Maximum execution time in seconds.
            cwd: Working directory for the command.
            shell: Whether to run through the shell.
            capture_output: Whether to capture stdout/stderr.

        Returns:
            CompletedProcess with returncode, stdout, stderr.
        """
        if cwd is not None:
            cwd = str(Path(cwd).resolve())

        kwargs: dict[str, Any] = {
            "timeout": timeout,
            "cwd": cwd,
            "shell": shell,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if capture_output:
            kwargs["stdout"] = subprocess.PIPE
            kwargs["stderr"] = subprocess.PIPE

        if self._is_windows() and isinstance(command, str):
            kwargs["shell"] = True

        return subprocess.run(command, **kwargs)

    def _expand_path(self, path_str: str) -> Path:
        """Expand user home and environment variables in a path.

        Args:
            path_str: Path string potentially containing ~ or $VAR.

        Returns:
            Expanded absolute Path.
        """
        expanded = os.path.expanduser(path_str)
        expanded = os.path.expandvars(expanded)
        return Path(expanded).resolve()

    def _get_temp_dir(self) -> Path:
        """Get a temporary directory appropriate for the OS.

        Returns:
            Path to a temporary directory.
        """
        if self._is_windows():
            temp = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))
        else:
            temp = Path("/tmp")
        return temp / "sago"

    @classmethod
    def to_langchain_tool(cls) -> Any:
        """Convert this tool to a LangChain-compatible tool.

        Returns:
            A LangChain StructuredTool instance.
        """
        from langchain_core.tools import StructuredTool

        def _execute(**kwargs: Any) -> str:
            tool = cls()
            return tool.run(**kwargs)

        async def _aexecute(**kwargs: Any) -> str:
            return _execute(**kwargs)

        args_schema = cls.args_model if cls.args_model else None

        return StructuredTool.from_function(
            func=_execute,
            coroutine=_aexecute,
            name=cls.name,
            description=cls.description,
            args_schema=args_schema,
        )
