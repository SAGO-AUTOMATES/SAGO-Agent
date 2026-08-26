"""Test Runner Tool - Run tests and report results.

Cross-platform test execution with auto-detection.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.test_runner")


class TestRunnerArgs(BaseModel):
    """Arguments for TestRunnerTool."""

    path: str = Field(default=".", description="Path to test file or directory")
    framework: str | None = Field(default=None, description="Test framework to use")
    pattern: str | None = Field(default=None, description="Test file pattern (e.g., 'test_*.py')")


class TestRunnerTool(BaseTool):
    """Tool for running tests across multiple frameworks."""

    name = "test_runner"
    description = "Run tests and report results. Auto-detects test framework."
    args_model = TestRunnerArgs

    _FRAMEWORK_MAP: dict[str, list[list[str]]] = {
        "python": [["pytest"], ["python", "-m", "unittest"], ["uv", "run", "pytest"]],
        "javascript": [
            ["bun", "test"],
            ["pnpm", "test"],
            ["yarn", "test"],
            ["npm", "test"],
            ["npx", "jest"],
        ],
        "typescript": [
            ["bun", "test"],
            ["pnpm", "test"],
            ["yarn", "test"],
            ["npm", "test"],
            ["npx", "jest"],
        ],
        "go": [["go", "test", "./..."]],
        "rust": [["cargo", "test"]],
        "ruby": [["bundle", "exec", "rspec"], ["ruby", "-m", "test"]],
        "java": [["mvn", "test"], ["gradle", "test"], ["./mvnw", "test"], ["./gradlew", "test"]],
        "php": [["phpunit"], ["vendor/bin/phpunit"], ["pest"]],
        "csharp": [["dotnet", "test"]],
        "swift": [["swift", "test"]],
        "kotlin": [["gradle", "test"], ["mvn", "test"]],
        "dart": [["dart", "test"]],
        "elixir": [["mix", "test"]],
        "haskell": [["stack", "test"], ["cabal", "test"]],
    }

    def _run(
        self,
        path: str = ".",
        framework: str | None = None,
        pattern: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Run tests.

        Args:
            path: Path to test.
            framework: Test framework.
            pattern: Test file pattern.

        Returns:
            Test results.
        """
        logger.debug(
            "Test execution started: path=%s, framework=%s, pattern=%s", path, framework, pattern
        )
        test_path = self._expand_path(path)

        if not test_path.exists():
            logger.warning("Test path not found: %s", test_path)
            return f"Error: Path not found: {test_path}"

        # Auto-detect framework
        if framework:
            logger.debug("Using specified framework: %s", framework)
            cmd = self._get_framework_cmd(framework, test_path, pattern)
        else:
            logger.debug("Auto-detecting test framework for: %s", test_path)
            cmd = self._auto_detect_framework(test_path, pattern)

        if not cmd:
            logger.warning("Could not detect test framework for: %s", test_path)
            return f"Could not detect test framework for: {test_path}"

        logger.info("Running tests: command=%s, cwd=%s", cmd, test_path)
        result = self._run_command(cmd, timeout=600, cwd=test_path)

        output_parts = [f"Command: {' '.join(cmd)}"]
        output_parts.append(f"Working directory: {test_path}")

        if result.stdout:
            output_parts.append(f"\n{result.stdout.strip()}")
        if result.stderr:
            output_parts.append(f"\nSTDERR:\n{result.stderr.strip()}")

        if result.returncode == 0:
            logger.info("All tests passed: command=%s", cmd)
            output_parts.append("\nAll tests passed!")
        else:
            logger.warning("Tests failed: command=%s, exit_code=%d", cmd, result.returncode)
            output_parts.append(f"\nExit code: {result.returncode}")

        return "\n".join(output_parts)

    def _auto_detect_framework(self, path: Path, pattern: str | None) -> list[str] | None:
        """Auto-detect test framework from project files with smart manager detection."""
        import shutil
        import sys

        def _which(cmd: str) -> str | None:
            # Use smart which (PATH + ensure_dep extensions)
            w = shutil.which(cmd)
            if w:
                return w
            try:
                from sago.tools.ensure_dep import which as smart_which

                return smart_which(cmd)
            except Exception:
                return None

        def _pytest_available() -> bool:
            try:
                import importlib.util

                return importlib.util.find_spec("pytest") is not None
            except Exception:
                return False

        # Helper: preferred JS test command based on lockfiles
        def _js_test_cmd(p: Path) -> list[str]:
            if (p / "bun.lockb").exists() and _which("bun"):
                return ["bun", "test"]
            if (p / "pnpm-lock.yaml").exists() and _which("pnpm"):
                return ["pnpm", "test"]
            if (p / "yarn.lock").exists() and _which("yarn"):
                return ["yarn", "test"]
            if _which("npm"):
                return ["npm", "test"]
            if _which("bun"):
                return ["bun", "test"]
            if _which("pnpm"):
                return ["pnpm", "test"]
            if _which("yarn"):
                return ["yarn", "test"]
            return ["npm", "test"]

        def _python_test_cmd(p: Path) -> list[str] | None:
            # Prefer uv if lockfile present
            if (p / "uv.lock").exists() and _which("uv"):
                return ["uv", "run", "pytest", str(p)]
            if _which("pytest"):
                return ["pytest", str(p)]
            if _pytest_available():
                return [sys.executable, "-m", "pytest", str(p)]
            return None

        # Check for Python test frameworks (smart uv vs pip)
        if (
            (path / "pytest.ini").exists()
            or (path / "pyproject.toml").exists()
            or (path / "uv.lock").exists()
        ):
            cmd = _python_test_cmd(path)
            if cmd:
                return cmd

        if (path / "setup.cfg").exists() or (path / "tox.ini").exists():
            cmd = _python_test_cmd(path)
            if cmd:
                return cmd

        # Check for Node.js (smart js manager)
        if (path / "package.json").exists():
            return _js_test_cmd(path)

        # Check for Go
        if list(path.glob("*.go")) or (path / "go.mod").exists():
            if _which("go"):
                return ["go", "test", "./..."]

        # Check for Rust
        if (path / "Cargo.toml").exists():
            if _which("cargo"):
                return ["cargo", "test"]

        # Check for Ruby
        if (path / "Gemfile").exists():
            if _which("bundle"):
                return ["bundle", "exec", "rspec"]
            if _which("rspec"):
                return ["rspec"]

        # Check for PHP
        if (
            (path / "composer.json").exists()
            or (path / "phpunit.xml").exists()
            or (path / "pest.php").exists()
        ):
            if (path / "vendor" / "bin" / "phpunit").exists():
                return ["vendor/bin/phpunit"]
            if _which("phpunit"):
                return ["phpunit"]
            if _which("pest"):
                return ["pest"]

        # Check for Java
        if (path / "pom.xml").exists():
            if (path / "mvnw").exists():
                return ["./mvnw", "test"]
            if _which("mvn"):
                return ["mvn", "test"]
        if (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            if (path / "gradlew").exists():
                return ["./gradlew", "test"]
            if _which("gradle"):
                return ["gradle", "test"]

        # Check for C#
        if list(path.glob("*.csproj")) or list(path.glob("*.sln")):
            if _which("dotnet"):
                return ["dotnet", "test"]

        # Check for Dart
        if (path / "pubspec.yaml").exists():
            if _which("dart"):
                return ["dart", "test"]

        # Pattern hint
        if pattern:
            if pattern.endswith(".py") and (_which("pytest") or _pytest_available()):
                cmd = _python_test_cmd(path)
                if cmd:
                    return cmd
            if pattern.endswith((".js", ".ts")):
                return _js_test_cmd(path)

        # Default to python if available (smart)
        cmd = _python_test_cmd(path)
        if cmd:
            return cmd
        if _which("pytest"):
            return ["pytest", str(path)]
        if _pytest_available():
            return [sys.executable, "-m", "pytest", str(path)]

        return None

    def _get_framework_cmd(self, framework: str, path: Path, pattern: str | None) -> list[str]:
        """Get command for a specific framework with smart installer selection."""
        import shutil
        import sys

        def _which(cmd: str) -> str | None:
            w = shutil.which(cmd)
            if w:
                return w
            try:
                from sago.tools.ensure_dep import which as smart_which

                return smart_which(cmd)
            except Exception:
                return None

        fw = framework.lower()
        # Smart: for python, prefer uv if available and lockfile exists
        if fw == "python":
            if (
                (path if path.is_file() else Path.cwd())
                and (Path.cwd() / "uv.lock").exists()
                and _which("uv")
            ):
                return (
                    ["uv", "run", "pytest", str(path)]
                    if path.is_file()
                    else ["uv", "run", "pytest", str(path)]
                )
            if path.is_file():
                if _which("pytest"):
                    return ["pytest", str(path)]
                # fallback to python -m pytest
                return [sys.executable, "-m", "pytest", str(path)]
        if fw in ("javascript", "typescript", "js", "ts", "node", "bun", "pnpm", "yarn", "npm"):
            # Detect preferred JS manager
            cwd = path if path.is_dir() else path.parent
            if (cwd / "bun.lockb").exists() and _which("bun"):
                return ["bun", "test"]
            if (cwd / "pnpm-lock.yaml").exists() and _which("pnpm"):
                return ["pnpm", "test"]
            if (cwd / "yarn.lock").exists() and _which("yarn"):
                return ["yarn", "test"]
            # Fallback to mapped command but prioritize available binary
            for candidate in (["bun", "test"], ["pnpm", "test"], ["yarn", "test"], ["npm", "test"]):
                if _which(candidate[0]):
                    return candidate
        cmds = self._FRAMEWORK_MAP.get(fw, [])
        if cmds:
            # Return first available command
            for cmd in cmds:
                if shutil.which(cmd[0]) or cmd[0] in ("python", "./mvnw", "./gradlew"):
                    if fw == "python" and path.is_file():
                        return ["pytest", str(path)]
                    return list(cmd)
            return list(cmds[0])
        return [framework, str(path)]
