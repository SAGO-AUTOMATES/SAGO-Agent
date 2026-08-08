"""Software Install Tool - Install software packages.

Cross-platform package manager support.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class SoftwareInstallArgs(BaseModel):
    """Arguments for SoftwareInstallTool."""

    package: str = Field(description="Package name to install")
    manager: Literal["auto", "apt", "yum", "dnf", "brew", "choco", "pip", "npm", "cargo"] = Field(default="auto", description="Package manager to use")
    version: str | None = Field(default=None, description="Specific version to install")
    sudo: bool = Field(default=False, description="Use sudo for installation")


class SoftwareInstallTool(BaseTool):
    """Tool for installing software packages across platforms."""

    name = "software_install"
    description = "Install software packages using system package managers."
    args_model = SoftwareInstallArgs

    _MANAGER_COMMANDS: dict[str, list[list[str]]] = {
        "apt": [["apt-get", "install", "-y"], ["sudo", "apt-get", "install", "-y"]],
        "yum": [["yum", "install", "-y"], ["sudo", "yum", "install", "-y"]],
        "dnf": [["dnf", "install", "-y"], ["sudo", "dnf", "install", "-y"]],
        "brew": [["brew", "install"]],
        "choco": [["choco", "install", "-y"]],
        "pip": [["pip", "install"], ["pip3", "install"]],
        "npm": [["npm", "install", "-g"]],
        "cargo": [["cargo", "install"]],
    }

    def _run(
        self,
        package: str,
        manager: str = "auto",
        version: str | None = None,
        sudo: bool = False,
        **kwargs: Any,
    ) -> str:
        """Install a software package.

        Args:
            package: Package name.
            manager: Package manager.
            version: Specific version.
            sudo: Use sudo.

        Returns:
            Installation result.
        """
        import shutil

        if manager == "auto":
            manager = self._detect_manager()

        if manager not in self._MANAGER_COMMANDS:
            return f"Error: Unknown package manager: {manager}"

        # Build package spec
        pkg_spec = package
        if version:
            if manager == "pip":
                pkg_spec = f"{package}=={version}"
            elif manager == "apt":
                pkg_spec = f"{package}={version}"
            elif manager == "npm":
                pkg_spec = f"{package}@{version}"

        # Get command
        sudo_idx = 1 if sudo else 0
        cmds = self._MANAGER_COMMANDS[manager]
        if sudo and len(cmds) > 1:
            cmd = list(cmds[1])
        else:
            cmd = list(cmds[0])

        cmd.append(pkg_spec)

        # Check if manager is available
        if not shutil.which(cmd[0]):
            return f"Error: {cmd[0]} is not installed or not in PATH"

        result = self._run_command(cmd, timeout=300)

        output_parts = [f"Installing {package} using {manager}..."]
        if result.stdout:
            output_parts.append(result.stdout.strip())
        if result.stderr:
            output_parts.append(result.stderr.strip())

        if result.returncode == 0:
            output_parts.insert(0, f"Successfully installed {package}")
        else:
            output_parts.insert(0, f"Failed to install {package} (exit code: {result.returncode})")

        return "\n".join(output_parts)

    def _detect_manager(self) -> str:
        """Auto-detect the appropriate package manager."""
        import shutil

        if self._is_windows():
            if shutil.which("choco"):
                return "choco"
            return "choco"

        if self._is_macos():
            if shutil.which("brew"):
                return "brew"
            return "brew"

        # Linux
        if shutil.which("apt-get"):
            return "apt"
        elif shutil.which("dnf"):
            return "dnf"
        elif shutil.which("yum"):
            return "yum"

        return "apt"
