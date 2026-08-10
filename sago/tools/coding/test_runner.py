"""Test Runner Tool - Run tests and report results.

Cross-platform test execution with auto-detection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


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
        "python": [["pytest"], ["python", "-m", "unittest"]],
        "javascript": [["npm", "test"], ["yarn", "test"], ["npx", "jest"]],
        "typescript": [["npm", "test"], ["yarn", "test"], ["npx", "jest"]],
        "go": [["go", "test", "./..."]],
        "rust": [["cargo", "test"]],
        "ruby": [["bundle", "exec", "rspec"], ["ruby", "-m", "test"]],
        "java": [["mvn", "test"], ["gradle", "test"]],
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
        test_path = self._expand_path(path)

        if not test_path.exists():
            return f"Error: Path not found: {test_path}"

        # Auto-detect framework
        if framework:
            cmd = self._get_framework_cmd(framework, test_path, pattern)
        else:
            cmd = self._auto_detect_framework(test_path, pattern)

        if not cmd:
            return f"Could not detect test framework for: {test_path}"

        result = self._run_command(cmd, timeout=600, cwd=test_path)

        output_parts = [f"Command: {' '.join(cmd)}"]
        output_parts.append(f"Working directory: {test_path}")

        if result.stdout:
            output_parts.append(f"\n{result.stdout.strip()}")
        if result.stderr:
            output_parts.append(f"\nSTDERR:\n{result.stderr.strip()}")

        if result.returncode == 0:
            output_parts.append("\nAll tests passed!")
        else:
            output_parts.append(f"\nExit code: {result.returncode}")

        return "\n".join(output_parts)

    def _auto_detect_framework(self, path: Path, pattern: str | None) -> list[str] | None:
        """Auto-detect test framework from project files."""
        import shutil

        # Check for Python test frameworks
        if (path / "pytest.ini").exists() or (path / "pyproject.toml").exists():
            if shutil.which("pytest"):
                return ["pytest", str(path)]

        if (path / "setup.cfg").exists() or (path / "tox.ini").exists():
            if shutil.which("pytest"):
                return ["pytest", str(path)]

        # Check for Node.js
        if (path / "package.json").exists():
            if shutil.which("npm"):
                return ["npm", "test"]

        # Check for Go
        if list(path.glob("*.go")):
            if shutil.which("go"):
                return ["go", "test", "./..."]

        # Check for Rust
        if (path / "Cargo.toml").exists():
            if shutil.which("cargo"):
                return ["cargo", "test"]

        # Check for Ruby
        if (path / "Gemfile").exists():
            if shutil.which("bundle"):
                return ["bundle", "exec", "rspec"]

        # Default to pytest if available
        if shutil.which("pytest"):
            return ["pytest", str(path)]

        return None

    def _get_framework_cmd(self, framework: str, path: Path, pattern: str | None) -> list[str]:
        """Get command for a specific framework."""
        cmds = self._FRAMEWORK_MAP.get(framework.lower(), [])
        if cmds:
            cmd = list(cmds[0])
            if framework.lower() == "python" and path.is_file():
                cmd = ["pytest", str(path)]
            return cmd
        return [framework, str(path)]
