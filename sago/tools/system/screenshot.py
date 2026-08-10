"""Screenshot Tool - Capture screenshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ScreenshotArgs(BaseModel):
    """Arguments for screenshot operations."""

    operation: str = Field(description="Operation: capture, capture-window, capture-area")
    output_path: str = Field(default="", description="Output file path")
    window_title: str = Field(default="", description="Window title for capture-window")
    region: str = Field(default="", description="Region for capture-area: x,y,width,height")


class Screenshot(BaseTool):
    """Tool for capturing screenshots."""

    name: str = "screenshot"
    description: str = "Capture screenshots of the desktop or specific windows."
    args_model: type[BaseModel] = ScreenshotArgs

    def _run(
        self,
        operation: str,
        output_path: str = "",
        window_title: str = "",
        region: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute screenshot operation."""
        try:
            output = Path(output_path) if output_path else self._get_temp_dir() / "screenshot.png"

            if self._is_linux():
                return self._capture_linux(operation, output, window_title, region)
            elif self._is_macos():
                return self._capture_macos(operation, output, window_title, region)
            elif self._is_windows():
                return self._capture_windows(operation, output, window_title, region)
            else:
                return "Error: Unsupported OS"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _capture_linux(
        self,
        operation: str,
        output: Path,
        window_title: str,
        region: str,
    ) -> str:
        """Capture screenshot on Linux."""
        if operation == "capture":
            result = self._run_command(f"scrot '{output}'", timeout=10)
            if result.returncode == 0:
                return f"Screenshot saved: {output}"
            # Try gnome-screenshot
            result = self._run_command(f"gnome-screenshot -f '{output}'", timeout=10)
            if result.returncode == 0:
                return f"Screenshot saved: {output}"
            return "Error: No screenshot tool found. Install scrot or gnome-screenshot"

        elif operation == "capture-area" and region:
            x, y, w, h = region.split(",")
            result = self._run_command(
                f"scrot -a {x},{y},{w},{h} '{output}'",
                timeout=10,
            )
            if result.returncode == 0:
                return f"Screenshot saved: {output}"
            return "Error capturing area"

        return f"Error: Unsupported operation '{operation}'"

    def _capture_macos(
        self,
        operation: str,
        output: Path,
        window_title: str,
        region: str,
    ) -> str:
        """Capture screenshot on macOS."""
        if operation == "capture":
            result = self._run_command(
                f"screencapture '{output}'",
                timeout=10,
            )
            if result.returncode == 0:
                return f"Screenshot saved: {output}"

        elif operation == "capture-window" and window_title:
            result = self._run_command(
                f"screencapture -l$(osascript -e 'tell application \"System Events\" to tell process \"{window_title}\" to get id of first window') '{output}'",
                timeout=15,
            )
            if result.returncode == 0:
                return f"Screenshot saved: {output}"

        return "Error: Screenshot failed"

    def _capture_windows(
        self,
        operation: str,
        output: Path,
        window_title: str,
        region: str,
    ) -> str:
        """Capture screenshot on Windows."""
        # Use PowerShell
        ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bitmap.Save('{output}')
$graphics.Dispose()
$bitmap.Dispose()
"""
        result = self._run_command(
            f"powershell -Command '{ps_script}'",
            timeout=15,
        )
        if result.returncode == 0:
            return f"Screenshot saved: {output}"
        return f"Error: {result.stderr}"


def get_tool() -> type[Screenshot]:
    """Get the tool class."""
    return Screenshot
