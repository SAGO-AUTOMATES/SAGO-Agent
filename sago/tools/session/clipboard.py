"""Clipboard Tool - Cross-platform clipboard operations.

Read from and write to the system clipboard.
"""

from __future__ import annotations

import base64
import logging
import platform
import subprocess
import sys
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.session.clipboard")


class ClipboardArgs(BaseModel):
    """Arguments for ClipboardTool."""

    operation: Literal["read", "write", "clear"] = Field(description="Clipboard operation")
    content: str | None = Field(default=None, description="Content to write to clipboard")


class ClipboardTool(BaseTool):
    """Tool for reading from and writing to the system clipboard."""

    name = "clipboard"
    description = "Read from or write to the system clipboard. Cross-platform support."
    args_model = ClipboardArgs

    def _run(
        self,
        operation: str,
        content: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Perform a clipboard operation.

        Args:
            operation: 'read', 'write', or 'clear'.
            content: Content to write (for 'write').

        Returns:
            Clipboard content or status message.
        """
        if operation == "read":
            return self._read_clipboard()
        elif operation == "write":
            if content is None:
                return "Error: content required for write operation"
            return self._write_clipboard(content)
        elif operation == "clear":
            return self._write_clipboard("")
        return f"Error: Unknown operation: {operation}"

    def _read_clipboard(self) -> str:
        """Read content from the system clipboard."""
        try:
            if self._is_macos():
                result = subprocess.run(
                    ["pbpaste"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            elif self._is_windows():
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                # Linux - try xclip, then xsel, then wl-clipboard
                for cmd in [
                    ["xclip", "-selection", "clipboard", "-o"],
                    ["xsel", "--output", "--clipboard"],
                    ["wl-paste"],
                ]:
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )
                        if result.returncode == 0:
                            return result.stdout
                    except FileNotFoundError:
                        continue
                return "Error: No clipboard tool found. Install xclip, xsel, or wl-clipboard."

            if result.returncode != 0:
                return f"Error reading clipboard: {result.stderr}"

            content = result.stdout
            if not content:
                return "Clipboard is empty"
            return content

        except Exception as e:
            return f"Error reading clipboard: {e}"

    def _is_macos(self) -> bool:
        return platform.system() == "Darwin"

    def _is_windows(self) -> bool:
        return platform.system() == "Windows"

    def _write_clipboard(self, content: str) -> str:
        """Write content to the system clipboard."""
        try:
            if self._is_macos():
                process = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                process.communicate(input=content.encode("utf-8"))
                if process.returncode != 0:
                    raise RuntimeError("pbcopy failed")
            elif self._is_windows():
                import shlex

                safe_content = shlex.quote(content)
                subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        f"Set-Clipboard -Value {safe_content}",
                    ],
                    timeout=10,
                )
            else:
                # Linux
                wrote = False
                for cmd in [
                    ["xclip", "-selection", "clipboard"],
                    ["xsel", "--input", "--clipboard"],
                    ["wl-copy"],
                ]:
                    try:
                        process = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                        process.communicate(input=content.encode("utf-8"))
                        if process.returncode == 0:
                            wrote = True
                            break
                    except FileNotFoundError:
                        continue
                if not wrote:
                    # Fallback: OSC 52 terminal clipboard — works in many terminals
                    # even when xclip/xsel not installed; also hint about Shift-select.
                    try:
                        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
                        # Write OSC 52 to stderr so it reaches terminal even inside TUI
                        sys.stderr.write(f"\x1b]52;c;{b64}\x07")
                        sys.stderr.flush()
                        # Also try stdout
                        sys.stdout.write(f"\x1b]52;c;{b64}\x07")
                        sys.stdout.flush()
                        if content:
                            return f"Clipboard updated via OSC 52 ({len(content)} chars) — tip: hold Shift while selecting text to copy natively"
                        return "Clipboard cleared (OSC 52)"
                    except Exception:
                        pass
                    hint = "Install xclip, xsel, or wl-clipboard. Tip: hold Shift while dragging to select text natively in most terminals."
                    return f"Error: No clipboard tool found. {hint}"

            if content:
                return f"Clipboard updated ({len(content)} chars)"
            return "Clipboard cleared"

        except Exception as e:
            return f"Error writing clipboard: {e}"
