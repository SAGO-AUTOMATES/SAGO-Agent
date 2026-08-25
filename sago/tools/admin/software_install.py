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
    manager: Literal[
        "auto",
        "apt",
        "yum",
        "dnf",
        "brew",
        "choco",
        "pip",
        "uv",
        "poetry",
        "pipx",
        "npm",
        "bun",
        "pnpm",
        "yarn",
        "cargo",
    ] = Field(default="auto", description="Package manager to use")
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
        "uv": [["uv", "pip", "install"]],
        "poetry": [["poetry", "add"]],
        "pipx": [["pipx", "install"]],
        "npm": [["npm", "install", "-g"]],
        "bun": [["bun", "add", "-g"]],
        "pnpm": [["pnpm", "add", "-g"]],
        "yarn": [["yarn", "global", "add"]],
        "cargo": [["cargo", "install"]],
    }

    # Heuristic: known python packages vs js packages for auto detection
    _PYTHON_PACKAGES = {
        "requests",
        "fastapi",
        "flask",
        "django",
        "pytest",
        "ruff",
        "black",
        "mypy",
        "pydantic",
        "httpx",
        "numpy",
        "pandas",
        "typer",
        "rich",
        "uvicorn",
        "sqlalchemy",
    }
    _JS_PACKAGES = {
        "typescript",
        "eslint",
        "prettier",
        "jest",
        "vitest",
        "react",
        "next",
        "express",
        "vue",
        "vite",
        "webpack",
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
            # Smart: infer python vs js vs system package, then detect preferred manager
            manager = self._detect_manager(package)

        if manager not in self._MANAGER_COMMANDS:
            return f"Error: Unknown package manager: {manager}"

        # Build package spec
        pkg_spec = package
        if version:
            if manager in ("pip", "uv"):
                pkg_spec = f"{package}=={version}"
            elif manager == "poetry":
                pkg_spec = f"{package}@{version}" if "@" not in package else package
            elif manager == "apt":
                pkg_spec = f"{package}={version}"
            elif manager in ("npm", "bun", "pnpm", "yarn"):
                pkg_spec = f"{package}@{version}"

        # Get command
        cmds = self._MANAGER_COMMANDS[manager]
        if sudo and len(cmds) > 1:
            cmd = list(cmds[1])
        else:
            cmd = list(cmds[0])

        cmd.append(pkg_spec)

        # Check if manager is available (smart which includes extra dirs)
        def _smart_which(c: str) -> str | None:
            w = shutil.which(c)
            if w:
                return w
            try:
                from sago.tools.ensure_dep import which as smart_which

                return smart_which(c)
            except Exception:
                return None

        if not _smart_which(cmd[0]):
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

    def _detect_manager(self, package: str | None = None) -> str:
        """Auto-detect the appropriate package manager with project-aware smarts.

        Order:
        - If package looks like python package -> prefer uv > poetry > pip
        - If package looks like js package -> prefer bun > pnpm > yarn > npm
        - Else fallback to system manager (apt/brew/choco)
        - Checks project lockfiles (uv.lock, poetry.lock, bun.lockb, pnpm-lock.yaml, yarn.lock)
        """
        import shutil
        from pathlib import Path

        pkg_lower = (package or "").lower()

        def _which(c: str) -> str | None:
            w = shutil.which(c)
            if w:
                return w
            try:
                from sago.tools.ensure_dep import which as smart_which

                return smart_which(c)
            except Exception:
                return None

        # Detect JS package manager from lockfiles
        def _preferred_js_manager() -> str | None:
            cwd = Path.cwd()
            # Check lockfiles in current + parent
            for parent in [cwd] + list(cwd.parents)[:3]:
                if (parent / "bun.lockb").exists() and _which("bun"):
                    return "bun"
                if (parent / "pnpm-lock.yaml").exists() and _which("pnpm"):
                    return "pnpm"
                if (parent / "yarn.lock").exists() and _which("yarn"):
                    return "yarn"
                if (parent / "package-lock.json").exists() and _which("npm"):
                    return "npm"
            # Fallback by availability priority
            for mgr in ("bun", "pnpm", "yarn", "npm"):
                if _which(mgr):
                    return mgr
            return None

        def _preferred_python_manager() -> str | None:
            cwd = Path.cwd()
            for parent in [cwd] + list(cwd.parents)[:3]:
                if (parent / "uv.lock").exists() and _which("uv"):
                    return "uv"
                if (parent / "poetry.lock").exists() and _which("poetry"):
                    return "poetry"
                if (parent / "Pipfile").exists() and _which("pipenv"):
                    return "pipx"
            # Check pyproject.toml for uv
            try:
                py = cwd / "pyproject.toml"
                if py.exists() and "[tool.uv" in py.read_text() and _which("uv"):
                    return "uv"
            except Exception:
                pass
            if _which("uv"):
                return "uv"
            if _which("pip"):
                return "pip"
            if _which("pip3"):
                return "pip"
            return None

        # Heuristic based on package name
        if pkg_lower and pkg_lower in self._JS_PACKAGES:
            js = _preferred_js_manager()
            if js:
                return js
        if pkg_lower and pkg_lower in self._PYTHON_PACKAGES:
            py = _preferred_python_manager()
            if py:
                return py

        # Generic: if package contains typical python vs js hints
        # If we have any js lockfile, prefer js manager for unknown packages that look like npm
        # If we have uv.lock, prefer uv for unknown packages
        if package:
            cwd = Path.cwd()
            has_js_lock = any(
                (cwd / f).exists()
                for f in ("bun.lockb", "pnpm-lock.yaml", "yarn.lock", "package-lock.json")
            )
            has_py_lock = (cwd / "uv.lock").exists() or (cwd / "poetry.lock").exists()
            if has_js_lock and not has_py_lock:
                js = _preferred_js_manager()
                if js:
                    return js
            if has_py_lock:
                py = _preferred_python_manager()
                if py:
                    return py
            # Fallback: try python manager if pip/uv available and package not system-like
            # If package has no system manager hint, try language managers first
            if "/" not in pkg_lower and not pkg_lower.startswith("lib"):
                py = _preferred_python_manager()
                # Only return python manager if package not obviously system package
                # For safety, check if system manager would handle it - prefer system for apt-like names
                pass

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

    # Backwards compat alias
    def _detect_python_manager(self) -> str:
        """Return preferred python manager (uv > pip)."""
        m = self._detect_manager("requests")
        return m if m in ("uv", "poetry", "pip", "pipx") else "pip"

    def _detect_js_manager(self) -> str:
        """Return preferred js manager (bun > pnpm > yarn > npm)."""
        m = self._detect_manager("typescript")
        return m if m in ("bun", "pnpm", "yarn", "npm") else "npm"
