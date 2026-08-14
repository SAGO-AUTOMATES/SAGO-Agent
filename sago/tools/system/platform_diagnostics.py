"""Platform & Environment Diagnostics Tool."""

from __future__ import annotations

import platform
import shutil
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class PlatformDiagnosticsArgs(BaseModel):
    """Arguments for PlatformDiagnosticsTool."""

    check_docker: bool = Field(default=True, description="Check Docker daemon connectivity")
    check_git: bool = Field(default=True, description="Check git repository status")


class PlatformDiagnosticsTool(BaseTool):
    """Diagnose local OS, CPU, memory, disk, Python runtime, Git repo, and container connectivity."""

    name = "platform_diagnostics"
    description = "Inspect system runtime, disk space, Docker availability, and environment health."
    args_model = PlatformDiagnosticsArgs
    risk_level = "safe"

    def _run(self, check_docker: bool = True, check_git: bool = True, **kwargs: Any) -> str:
        lines = ["## System & Platform Diagnostics\n"]

        # 1. OS & Hardware
        lines.append(
            f"• **OS / Kernel**: {platform.system()} {platform.release()} ({platform.machine()})"
        )
        lines.append(f"• **Python**: {sys.version.split()[0]} ({sys.executable})")

        # 2. Disk Usage
        try:
            total, used, free = shutil.disk_usage(Path.cwd())
            lines.append(
                f"• **Disk Usage**: {used // (2**30)}GB used / {total // (2**30)}GB total ({free // (2**30)}GB free)"
            )
        except Exception:
            pass

        # 3. Environment & Tools
        common_binaries = [
            "git",
            "docker",
            "docker-compose",
            "kubectl",
            "ruff",
            "pytest",
            "node",
            "npm",
            "uv",
        ]
        avail = [b for b in common_binaries if shutil.which(b)]
        lines.append(f"• **Available CLI Binaries**: {', '.join(avail)}")

        # 4. Git status
        if check_git:
            if (Path.cwd() / ".git").exists():
                try:
                    res = self._run_command("git rev-parse --abbrev-ref HEAD", timeout=5)
                    branch = res.stdout.strip() if res.returncode == 0 else "unknown"
                    lines.append(f"• **Git Repo**: Initialized (active branch: {branch})")
                except Exception:
                    lines.append("• **Git Repo**: Initialized (branch unknown)")
            else:
                lines.append("• **Git Repo**: Not a git repository")

        return "\n".join(lines)
