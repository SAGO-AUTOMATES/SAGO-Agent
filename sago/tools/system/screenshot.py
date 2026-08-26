"""Screenshot Tool - Capture screenshots."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.system.screenshot")


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
        logger.debug(
            "screenshot called: operation=%s, output=%s", operation, output_path or "<temp>"
        )
        try:
            output = Path(output_path) if output_path else self._get_temp_dir() / "screenshot.png"

            if self._is_linux():
                return self._capture_linux(operation, output, window_title, region)
            elif self._is_macos():
                return self._capture_macos(operation, output, window_title, region)
            elif self._is_windows():
                return self._capture_windows(operation, output, window_title, region)
            else:
                logger.warning("Unsupported OS for screenshot")
                return "Error: Unsupported OS"

        except Exception as e:
            logger.error("Screenshot operation failed: operation=%s, error=%s", operation, e)
            return f"Error: {type(e).__name__}: {e}"

    def _capture_linux(
        self,
        operation: str,
        output: Path,
        window_title: str,
        region: str,
    ) -> str:
        """Capture screenshot on Linux."""
        import shlex

        output_escaped = shlex.quote(str(output))
        if operation == "capture":
            logger.info("Capturing Linux screenshot: output=%s", output)
            result = self._run_command(f"scrot {output_escaped}", timeout=10)
            if result.returncode == 0:
                logger.info("Screenshot saved via scrot: %s", output)
                return f"Screenshot saved: {output}"
            # Try gnome-screenshot
            logger.debug("scrot failed, trying gnome-screenshot")
            result = self._run_command(f"gnome-screenshot -f {output_escaped}", timeout=10)
            if result.returncode == 0:
                logger.info("Screenshot saved via gnome-screenshot: %s", output)
                return f"Screenshot saved: {output}"
            logger.error("No screenshot tool found on Linux")
            return "Error: No screenshot tool found. Install scrot or gnome-screenshot"

        elif operation == "capture-area" and region:
            parts = region.split(",")
            if len(parts) != 4:
                return "Error: region must be x,y,width,height"
            x, y, w, h = [p.strip() for p in parts]
            logger.info("Capturing Linux area screenshot: region=%s,%s,%s,%s", x, y, w, h)
            result = self._run_command(
                f"scrot -a {x},{y},{w},{h} {output_escaped}",
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Area screenshot saved: %s", output)
                return f"Screenshot saved: {output}"
            logger.error("Failed to capture area screenshot")
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
        import shlex

        output_escaped = shlex.quote(str(output))
        if operation == "capture":
            logger.info("Capturing macOS screenshot: output=%s", output)
            result = self._run_command(
                f"screencapture {output_escaped}",
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Screenshot saved: %s", output)
                return f"Screenshot saved: {output}"

        elif operation == "capture-window" and window_title:
            safe_title = shlex.quote(window_title)
            logger.info("Capturing macOS window screenshot: window=%s", window_title)
            result = self._run_command(
                f"screencapture -l$(osascript -e 'tell application \"System Events\" to tell process {safe_title} to get id of first window') {output_escaped}",
                timeout=15,
            )
            if result.returncode == 0:
                logger.info("Window screenshot saved: %s", output)
                return f"Screenshot saved: {output}"

        logger.error("macOS screenshot failed: operation=%s", operation)
        return "Error: Screenshot failed"

    def _capture_windows(
        self,
        operation: str,
        output: Path,
        window_title: str,
        region: str,
    ) -> str:
        """Capture screenshot on Windows."""
        logger.info("Capturing Windows screenshot: output=%s", output)
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
            logger.info("Windows screenshot saved: %s", output)
            return f"Screenshot saved: {output}"
        logger.error("Windows screenshot failed: stderr=%s", result.stderr)
        return f"Error: {result.stderr}"


def get_tool() -> type[Screenshot]:
    """Get the tool class."""
    return Screenshot
