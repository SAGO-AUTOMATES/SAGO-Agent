"""OS Detector Tool - Detect operating system and system information.

Cross-platform system information gathering.
"""

from __future__ import annotations

import logging
import os
import platform
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.errors import log_error

logger = logging.getLogger("sago.tools.system.os_detector")


class OSDetectorArgs(BaseModel):
    """Arguments for OSDetectorTool."""

    detailed: bool = Field(default=False, description="Include detailed system info")


class OSDetectorTool(BaseTool):
    """Tool for detecting operating system and system information."""

    name = "os_detector"
    description = "Detect the operating system and gather system information."
    args_model = OSDetectorArgs

    def _run(
        self,
        detailed: bool = False,
        **kwargs: Any,
    ) -> str:
        """Detect OS and system information.

        Args:
            detailed: Include detailed info.

        Returns:
            System information.
        """
        logger.debug("os_detector called: detailed=%s", detailed)
        logger.info(
            "Detecting OS: system=%s, release=%s, machine=%s",
            platform.system(),
            platform.release(),
            platform.machine(),
        )

        info = [
            "=== System Information ===",
            f"OS: {platform.system()}",
            f"OS Release: {platform.release()}",
            f"OS Version: {platform.version()}",
            f"Machine: {platform.machine()}",
            f"Processor: {platform.processor() or 'N/A'}",
            f"Python: {platform.python_version()}",
            f"Architecture: {platform.architecture()[0]}",
            f"Hostname: {platform.node()}",
        ]

        if detailed:
            info.append("\n=== Detailed Info ===")
            info.append(f"Platform: {platform.platform()}")
            info.append(f"CPU count: {os.cpu_count() or 'N/A'}")

            # Memory info
            try:
                import psutil

                mem = psutil.virtual_memory()
                info.append(f"Total memory: {mem.total // (1024**3)} GB")
                info.append(f"Available memory: {mem.available // (1024**3)} GB")
                info.append(f"Memory usage: {mem.percent}%")
            except ImportError:
                info.append("Memory: psutil not installed")

            # Disk info
            try:
                import psutil

                disk = psutil.disk_usage("/")
                info.append(f"Disk total: {disk.total // (1024**3)} GB")
                info.append(f"Disk free: {disk.free // (1024**3)} GB")
            except Exception as e:
                log_error("Failed to gather disk usage info", e)

            # Environment
            info.append(f"\nShell: {os.environ.get('SHELL', os.environ.get('COMSPEC', 'N/A'))}")
            info.append(f"User: {os.environ.get('USER', os.environ.get('USERNAME', 'N/A'))}")
            info.append(f"Home: {os.path.expanduser('~')}")

        return "\n".join(info)
