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

    # Linter commands by language extension - comprehensive coverage
    _LINTER_MAP: dict[str, list[list[str]]] = {
        ".py": [["ruff", "check"], ["flake8"], ["pylint"], ["pycodestyle"]],
        ".pyi": [["ruff", "check"], ["flake8"]],
        ".js": [["eslint"], ["biome", "lint"], ["standard"]],
        ".mjs": [["eslint"], ["biome", "lint"]],
        ".cjs": [["eslint"]],
        ".ts": [["eslint"], ["biome", "lint"], ["tslint"]],
        ".mts": [["eslint"]],
        ".jsx": [["eslint"], ["eslint", "--ext", ".jsx"]],
        ".tsx": [["eslint"], ["eslint", "--ext", ".tsx"]],
        ".vue": [["eslint"]],
        ".svelte": [["eslint"]],
        ".go": [["golangci-lint", "run"], ["go", "vet"]],
        ".rs": [["cargo", "clippy", "--", "-D", "warnings"]],
        ".rb": [["rubocop"], ["standardrb"]],
        ".java": [["checkstyle"], ["pmd"]],
        ".kt": [["ktlint"], ["detekt"]],
        ".scala": [["scalac", "-Xlint"]],
        ".php": [["phpcs"], ["phpstan", "analyse"], ["psalm"]],
        ".c": [["cppcheck", "--enable=all"], ["clang-tidy"]],
        ".h": [["cppcheck", "--enable=all"], ["clang-tidy"]],
        ".cpp": [["cppcheck", "--enable=all"], ["clang-tidy"]],
        ".hpp": [["cppcheck", "--enable=all"], ["clang-tidy"]],
        ".cc": [["cppcheck", "--enable=all"]],
        ".cs": [["dotnet", "format", "--verify-no-changes"]],
        ".swift": [["swiftlint", "lint"]],
        ".dart": [["dart", "analyze"]],
        ".lua": [["luacheck"]],
        ".pl": [["perlcritic"]],
        ".r": [["lintr"]],
        ".yaml": [["yamllint"]],
        ".yml": [["yamllint"]],
        ".json": [["jsonlint"], ["biome", "lint"]],
        ".toml": [["taplo", "check"]],
        ".xml": [["xmllint", "--noout"]],
        ".html": [["htmlhint"], ["tidy", "-e"]],
        ".css": [["stylelint"]],
        ".scss": [["stylelint"]],
        ".less": [["stylelint"]],
        ".sh": [["shellcheck"]],
        ".bash": [["shellcheck"]],
        ".zsh": [["shellcheck"]],
        ".sql": [["sqlfluff", "lint"], ["sqlint"]],
        ".md": [["markdownlint"]],
        ".dockerfile": [["hadolint"]],
    }

    # Fallback mapping for directories: try to detect language from common files
    _DIR_HINTS: list[tuple[str, str]] = [
        ("pyproject.toml", ".py"),
        ("package.json", ".js"),
        ("Cargo.toml", ".rs"),
        ("go.mod", ".go"),
        ("pom.xml", ".java"),
        ("build.gradle", ".java"),
        ("composer.json", ".php"),
        ("Gemfile", ".rb"),
        ("pubspec.yaml", ".dart"),
    ]

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

        # Determine file extension (smart for directories)
        if path.is_file():
            ext = path.suffix.lower()
            # Special case: Dockerfile without extension
            if path.name.lower() == "dockerfile":
                ext = ".dockerfile"
        else:
            ext = self._infer_dir_extension(path)

        # Find available linter
        if linter:
            linter_cmd = [linter]
        else:
            linter_cmd = self._find_linter(ext)

        if not linter_cmd:
            return f"No linter found for extension: {ext} (tried {ext}; install ruff/eslint/golangci-lint etc.)"

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
        """Find an available linter for the given extension (smart which)."""
        import shutil

        def _which(c: str) -> str | None:
            w = shutil.which(c)
            if w:
                return w
            try:
                from sago.tools.ensure_dep import which as smart_which

                return smart_which(c)
            except Exception:
                return None

        linters = self._LINTER_MAP.get(ext, [])
        for linter_cmd in linters:
            if _which(linter_cmd[0]):
                return linter_cmd
        return None

    def _infer_dir_extension(self, path) -> str:
        """Infer extension for a directory by looking at config files and file samples."""
        from pathlib import Path as _P

        p = _P(path)
        for hint_file, ext in self._DIR_HINTS:
            if (p / hint_file).exists():
                return ext
        # Sample files in directory
        try:
            for child in p.iterdir():
                if child.is_file() and child.suffix.lower() in self._LINTER_MAP:
                    return child.suffix.lower()
        except Exception:
            pass
        return ".py"

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
        if name == "biome":
            return " ".join(["biome", "lint", "--write", path])
        if name == "golangci-lint":
            return " ".join(["golangci-lint", "run", "--fix", path])
        if name == "rubocop":
            return " ".join(["rubocop", "-A", path])
        if name == "phpcs":
            return " ".join(["phpcbf", path])
        if name == "black":
            return " ".join(["black", path])
        if name == "isort":
            return " ".join(["isort", path])
        # Generic fallback: append the common --fix flag.
        return " ".join(linter_cmd + ["--fix", path])
