"""Linter Tool - Run linting tools on code.

Cross-platform linting with auto-detection of linters.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class LinterArgs(BaseModel):
    """Arguments for LinterTool."""

    file_path: str = Field(description="Path to the file or directory to lint")
    linter: str | None = Field(
        default=None, description="Specific linter to use (auto-detect if not set)"
    )
    fix: bool = Field(default=False, description="Attempt to auto-fix issues")


class LinterTool(BaseTool):
    """Tool for running linters on code files."""

    name = "linter"
    description = "Run linters on code files. Auto-detects appropriate linter for the language."
    args_model = LinterArgs

    # Linter commands by language extension
    _LINTER_MAP: dict[str, list[list[str]]] = {
        ".py": [["ruff", "check"], ["flake8"], ["pylint"]],
        ".js": [["eslint"], ["standard"]],
        ".ts": [["eslint"], ["tslint"]],
        ".jsx": [["eslint"], ["eslint", "--ext", ".jsx"]],
        ".tsx": [["eslint"], ["eslint", "--ext", ".tsx"]],
        ".go": [["golangci-lint", "run"]],
        ".rs": [["clippy", "--", "-D", "warnings"]],
        ".rb": [["rubocop"]],
        ".java": [["checkstyle"]],
        ".yaml": [["yamllint"]],
        ".yml": [["yamllint"]],
        ".json": [["jsonlint"]],
        ".sh": [["shellcheck"]],
        ".bash": [["shellcheck"]],
    }

    def _run(
        self,
        file_path: str,
        linter: str | None = None,
        fix: bool = False,
        **kwargs: Any,
    ) -> str:
        """Run linter on code.

        Args:
            file_path: Path to lint.
            linter: Specific linter command.
            fix: Auto-fix issues.

        Returns:
            Linting results.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: Path not found: {path}"

        # Determine file extension
        if path.is_file():
            ext = path.suffix.lower()
        else:
            ext = ".py"  # Default for directories

        # Find available linter
        if linter:
            linter_cmd = [linter]
        else:
            linter_cmd = self._find_linter(ext)

        if not linter_cmd:
            return f"No linter found for extension: {ext}"

        # When autofix is requested, run the linter's fix command first so that
        # fixes are actually applied to the file before reporting results.
        if fix:
            fix_cmd = self._build_fix_command(linter_cmd, str(path))
            self._run_command(fix_cmd, timeout=120)

        # Build report command and execute
        cmd = " ".join(linter_cmd + [str(path)])
        result = self._run_command(cmd, timeout=120)

        output_parts = [f"Linter: {linter_cmd[0]}"]
        output_parts.append(f"Path: {path}")

        if result.stdout:
            output_parts.append(f"\nOutput:\n{result.stdout.strip()}")
        if result.stderr:
            output_parts.append(f"\nErrors:\n{result.stderr.strip()}")

        if result.returncode == 0:
            output_parts.append("\nLinting passed!")
        else:
            output_parts.append(f"\nExit code: {result.returncode}")

        return "\n".join(output_parts)

    def _find_linter(self, ext: str) -> list[str] | None:
        """Find an available linter for the given extension."""
        import shutil

        linters = self._LINTER_MAP.get(ext, [])
        for linter_cmd in linters:
            if shutil.which(linter_cmd[0]):
                return linter_cmd
        return None

    def _build_fix_command(self, linter_cmd: list[str], path: str) -> str:
        """Build the autofix command for the given linter.

        The returned command is a shell string suitable for ``_run_command``
        (which runs with ``shell=True``).
        """
        name = linter_cmd[0]
        if name == "ruff":
            return " ".join(["ruff", "check", "--fix", path])
        if name == "eslint":
            return " ".join(["eslint", "--fix", path])
        if name == "black":
            return " ".join(["black", path])
        if name == "isort":
            return " ".join(["isort", path])
        # Generic fallback: append the common --fix flag.
        return " ".join(linter_cmd + ["--fix", path])
