"""Environment Info Tool - Get detailed environment information."""

from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.env_info")


class EnvInfoArgs(BaseModel):
    """Arguments for environment info."""

    operation: str = Field(description="Operation: system, disk, memory, network, python, node")
    detail: str = Field(default="basic", description="Detail level: basic, full")


class EnvInfo(BaseTool):
    """Tool for getting detailed environment information."""

    name: str = "env_info"
    description: str = (
        "Get detailed environment information: system, disk, memory, "
        "network, Python, Node.js, and more."
    )
    args_model: type[BaseModel] | None = EnvInfoArgs

    def _run(
        self,
        operation: str,
        detail: str = "basic",
        **kwargs: Any,
    ) -> str:
        """Execute environment info operation."""
        try:
            if operation in ("system", "full"):
                detail_level = "full" if operation == "full" else detail
                return self._get_system_info(detail_level)
            elif operation == "disk":
                return self._get_disk_info()
            elif operation == "memory":
                return self._get_memory_info()
            elif operation == "network":
                return self._get_network_info()
            elif operation == "python":
                return self._get_python_info()
            elif operation == "node":
                return self._get_node_info()
            elif operation == "env":
                return self._get_env_vars()
            else:
                return f"Error: Invalid operation '{operation}'"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _get_system_info(self, detail: str) -> str:
        """Get system information."""
        info = [
            "System Information:",
            f"  OS: {platform.system()} {platform.release()}",
            f"  Platform: {platform.platform()}",
            f"  Machine: {platform.machine()}",
            f"  Processor: {platform.processor() or 'N/A'}",
            f"  Python: {platform.python_version()}",
            f"  Hostname: {platform.node()}",
        ]

        if detail == "full":
            info.extend(
                [
                    f"  OS Name: {os.name}",
                    f"  Architecture: {platform.architecture()[0]}",
                ]
            )

        return "\n".join(info)

    def _get_disk_info(self) -> str:
        """Get disk information."""
        try:
            import shutil

            total, used, free = shutil.disk_usage("/")
            return (
                f"Disk Information:\n"
                f"  Total: {total // (1024**3)} GB\n"
                f"  Used: {used // (1024**3)} GB\n"
                f"  Free: {free // (1024**3)} GB\n"
                f"  Usage: {(used / total) * 100:.1f}%"
            )
        except Exception as e:
            return f"Error getting disk info: {e}"

    def _get_memory_info(self) -> str:
        """Get memory information."""
        try:
            # Try psutil first
            import psutil

            mem = psutil.virtual_memory()
            return (
                f"Memory Information:\n"
                f"  Total: {mem.total // (1024**3)} GB\n"
                f"  Available: {mem.available // (1024**3)} GB\n"
                f"  Used: {mem.used // (1024**3)} GB\n"
                f"  Usage: {mem.percent}%"
            )
        except ImportError:
            # Fallback to /proc/meminfo on Linux
            if self._is_linux():
                try:
                    with open("/proc/meminfo") as f:
                        lines = f.readlines()
                    for line in lines:
                        if line.startswith("MemTotal"):
                            total = int(line.split()[1]) // 1024
                            return f"Memory: {total} MB total"
                except Exception as e:
                    logger.debug("Failed to read /proc/meminfo: %s", e)
        return "Memory Information: unavailable (install psutil)"

    def _get_network_info(self) -> str:
        """Get network information."""
        try:
            import socket

            hostname = socket.gethostname()
            try:
                ip = socket.gethostbyname(hostname)
            except Exception:
                ip = "N/A"

            info = [
                "Network Information:",
                f"  Hostname: {hostname}",
                f"  IP Address: {ip}",
            ]

            # Try to get interface info
            result = self._run_command(
                "ip addr show 2>/dev/null || ifconfig 2>/dev/null", timeout=5
            )
            if result.returncode == 0:
                # Extract IPs
                import re

                ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout)
                if ips:
                    info.append(f"  Interfaces: {', '.join(ips[:3])}")

            return "\n".join(info)
        except Exception as e:
            return f"Error: {e}"

    def _get_python_info(self) -> str:
        """Get Python environment information with smart manager detection."""
        info = [
            "Python Information:",
            f"  Version: {platform.python_version()}",
            f"  Implementation: {platform.python_implementation()}",
            f"  Compiler: {platform.python_compiler()}",
            f"  Executable: {sys.executable}",
        ]

        # Detect preferred manager (uv vs pip vs poetry)
        from pathlib import Path

        cwd = Path.cwd()
        preferred = "pip"
        if (cwd / "uv.lock").exists():
            preferred = "uv"
        elif (cwd / "poetry.lock").exists():
            preferred = "poetry"
        else:
            try:
                if (cwd / "pyproject.toml").exists() and "[tool.uv" in (
                    cwd / "pyproject.toml"
                ).read_text():
                    preferred = "uv"
            except Exception:
                pass
            # Check which binary exists
            import shutil

            if shutil.which("uv"):
                preferred = "uv (available)"

        info.append(f"  Preferred manager: {preferred}")

        # uv version if available
        result = self._run_command("uv --version 2>/dev/null", timeout=5)
        if result.returncode == 0:
            info.append(f"  uv: {result.stdout.strip()}")

        # pip version
        result = self._run_command("pip --version 2>/dev/null", timeout=5)
        if result.returncode == 0:
            info.append(f"  pip: {result.stdout.strip().splitlines()[0][:80]}")

        # poetry version
        result = self._run_command("poetry --version 2>/dev/null", timeout=5)
        if result.returncode == 0:
            info.append(f"  poetry: {result.stdout.strip()}")

        # Packages count via preferred manager
        result = self._run_command(
            "uv pip list 2>/dev/null | wc -l || pip list 2>/dev/null | wc -l", timeout=10
        )
        if result.returncode == 0:
            count = result.stdout.strip()
            info.append(f"  Packages: {count}")

        return "\n".join(info)

    def _get_node_info(self) -> str:
        """Get Node.js environment information with smart manager detection."""
        result = self._run_command("node --version 2>/dev/null", timeout=5)
        has_node = result.returncode == 0
        info = []
        if has_node:
            info.append("Node.js Information:")
            info.append(f"  Version: {result.stdout.strip()}")
        else:
            info.append("Node.js Information: not found (but checking JS managers)")

        # Detect preferred JS manager from lockfiles
        from pathlib import Path

        cwd = Path.cwd()
        preferred = "npm"
        if (cwd / "bun.lockb").exists():
            preferred = "bun (lockfile)"
        elif (cwd / "pnpm-lock.yaml").exists():
            preferred = "pnpm (lockfile)"
        elif (cwd / "yarn.lock").exists():
            preferred = "yarn (lockfile)"
        elif (cwd / "package-lock.json").exists():
            preferred = "npm (lockfile)"
        info.append(f"  Preferred manager: {preferred}")

        for mgr, cmd in [
            ("npm", "npm --version 2>/dev/null"),
            ("yarn", "yarn --version 2>/dev/null"),
            ("pnpm", "pnpm --version 2>/dev/null"),
            ("bun", "bun --version 2>/dev/null"),
        ]:
            result = self._run_command(cmd, timeout=5)
            if result.returncode == 0:
                info.append(f"  {mgr}: {result.stdout.strip()}")

        # deno version
        result = self._run_command("deno --version 2>/dev/null | head -1", timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            info.append(f"  deno: {result.stdout.strip()}")

        return "\n".join(info)

    def _get_env_vars(self) -> str:
        """Get relevant environment variables."""
        relevant_vars = [
            "HOME",
            "USER",
            "SHELL",
            "PATH",
            "LANG",
            "TERM",
            "PYTHONPATH",
            "NODE_PATH",
            "GOPATH",
            "CARGO_HOME",
            "AWS_REGION",
            "GCP_PROJECT",
            "AZURE_SUBSCRIPTION",
        ]

        info = ["Environment Variables:"]
        for var in relevant_vars:
            value = os.environ.get(var)
            if value:
                # Truncate long values
                if len(value) > 50:
                    value = value[:50] + "..."
                info.append(f"  {var}={value}")

        return "\n".join(info)


def get_tool() -> type[EnvInfo]:
    """Get the tool class."""
    return EnvInfo
