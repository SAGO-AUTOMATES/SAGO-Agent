"""Formatter Tool - Format code according to style standards.

Cross-platform code formatting with auto-detection.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.formatter")


class FormatterArgs(BaseModel):
    """Arguments for FormatterTool."""

    file_path: str = Field(description="Path to the file or directory to format")
    formatter: str | None = Field(default=None, description="Specific formatter to use")


class FormatterTool(BaseTool):
    """Tool for formatting code files."""

    name = "formatter"
    description = "Format code according to language-specific style standards."
    args_model = FormatterArgs

    _FORMATTER_MAP: dict[str, list[list[str]]] = {
        ".py": [["ruff", "format"], ["black"], ["autopep8"], ["yapf", "-i"]],
        ".pyi": [["ruff", "format"], ["black"]],
        ".js": [["biome", "format", "--write"], ["prettier", "--write"], ["eslint", "--fix"]],
        ".mjs": [["biome", "format", "--write"], ["prettier", "--write"]],
        ".cjs": [["prettier", "--write"]],
        ".ts": [["biome", "format", "--write"], ["prettier", "--write"], ["eslint", "--fix"]],
        ".mts": [["prettier", "--write"]],
        ".jsx": [["prettier", "--write"], ["biome", "format", "--write"]],
        ".tsx": [["prettier", "--write"], ["biome", "format", "--write"]],
        ".vue": [["prettier", "--write"]],
        ".svelte": [["prettier", "--write"]],
        ".json": [["biome", "format", "--write"], ["prettier", "--write"], ["jq", "."]],
        ".jsonc": [["prettier", "--write"]],
        ".go": [["gofmt", "-w"], ["goimports", "-w"], ["gofumpt", "-w"]],
        ".rs": [["rustfmt"]],
        ".rb": [["rubocop", "-A"], ["standardrb", "--fix"]],
        ".java": [["google-java-format", "-i"]],
        ".kt": [["ktlint", "--format"]],
        ".scala": [["scalafmt"]],
        ".php": [["phpcbf"], ["php-cs-fixer", "fix"]],
        ".c": [["clang-format", "-i"]],
        ".h": [["clang-format", "-i"]],
        ".cpp": [["clang-format", "-i"]],
        ".hpp": [["clang-format", "-i"]],
        ".cs": [["dotnet", "format"]],
        ".swift": [["swiftformat"]],
        ".dart": [["dart", "format"]],
        ".lua": [["stylua"]],
        ".sh": [["shfmt", "-w"], ["beautysh"]],
        ".bash": [["shfmt", "-w"]],
        ".zsh": [["shfmt", "-w"]],
        ".yaml": [["prettier", "--write"]],
        ".yml": [["prettier", "--write"]],
        ".toml": [["taplo", "format"]],
        ".xml": [["xmllint", "--format"]],
        ".html": [["prettier", "--write"], ["tidy", "-m"]],
        ".css": [["prettier", "--write"], ["stylelint", "--fix"]],
        ".scss": [["prettier", "--write"]],
        ".less": [["prettier", "--write"]],
        ".sql": [["sqlfluff", "format"], ["pg_format"]],
        ".md": [["prettier", "--write"]],
        ".dockerfile": [["hadolint"]],
    }

    _DIR_HINTS: list[tuple[str, str]] = [
        ("pyproject.toml", ".py"),
        ("package.json", ".js"),
        ("Cargo.toml", ".rs"),
        ("go.mod", ".go"),
        ("pom.xml", ".java"),
        ("build.gradle", ".java"),
        ("composer.json", ".php"),
        ("Gemfile", ".rb"),
    ]

    def _run(
        self,
        file_path: str,
        formatter: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Format code files.

        Args:
            file_path: Path to format.
            formatter: Specific formatter command.

        Returns:
            Formatting results.
        """
        logger.debug("Formatting started: file_path=%s, formatter=%s", file_path, formatter)
        path = self._expand_path(file_path)

        if not path.exists():
            logger.warning("Path not found for formatting: %s", path)
            return f"Error: Path not found: {path}"

        if path.is_file():
            ext = path.suffix.lower()
            if path.name.lower() == "dockerfile":
                ext = ".dockerfile"
        else:
            ext = self._infer_dir_extension(path)

        logger.debug("Extension detected: ext=%s, path=%s", ext, path)

        if formatter:
            formatter_cmd = [formatter, str(path)]
        else:
            formatter_cmd = self._find_formatter(ext)

        if not formatter_cmd:
            logger.warning("No formatter found for extension: %s", ext)
            return (
                f"No formatter found for extension: {ext} (install ruff/prettier/clang-format etc.)"
            )

        logger.info("Using formatter: %s for path=%s", formatter_cmd[0], path)

        cmd = formatter_cmd + [str(path)]
        logger.debug("Running format command: %s", cmd)
        result = self._run_command(cmd, timeout=120)

        output_parts = [f"Formatter: {formatter_cmd[0]}"]
        output_parts.append(f"Path: {path}")

        if result.returncode == 0:
            logger.info("Formatting succeeded: formatter=%s, path=%s", formatter_cmd[0], path)
            output_parts.append("Formatted successfully!")
        else:
            logger.warning(
                "Formatting failed: formatter=%s, path=%s, exit_code=%d",
                formatter_cmd[0],
                path,
                result.returncode,
            )
            output_parts.append(f"Exit code: {result.returncode}")
            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr.strip()}")

        return "\n".join(output_parts)

    def _find_formatter(self, ext: str) -> list[str] | None:
        """Find an available formatter for the extension (smart which)."""
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

        formatters = self._FORMATTER_MAP.get(ext, [])
        for fmt_cmd in formatters:
            if _which(fmt_cmd[0]):
                return list(fmt_cmd)
        return None

    def _infer_dir_extension(self, path) -> str:
        """Infer extension for a directory."""
        from pathlib import Path as _P

        p = _P(path)
        for hint_file, ext in self._DIR_HINTS:
            if (p / hint_file).exists():
                return ext
        try:
            for child in p.iterdir():
                if child.is_file() and child.suffix.lower() in self._FORMATTER_MAP:
                    return child.suffix.lower()
        except Exception:
            pass
        return ".py"
