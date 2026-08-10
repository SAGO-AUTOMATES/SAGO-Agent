"""Formatter Tool - Format code according to style standards.

Cross-platform code formatting with auto-detection.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


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
        ".py": [["ruff", "format"], ["black"], ["autopep8"]],
        ".js": [["prettier", "--write"], ["eslint", "--fix"]],
        ".ts": [["prettier", "--write"], ["eslint", "--fix"]],
        ".jsx": [["prettier", "--write"]],
        ".tsx": [["prettier", "--write"]],
        ".go": [["gofmt", "-w"], ["goimports", "-w"]],
        ".rs": [["rustfmt"]],
        ".rb": [["rubocop", "-A"]],
        ".java": [["google-java-format", "-i"]],
        ".yaml": [["prettier", "--write"]],
        ".json": [["prettier", "--write"]],
        ".md": [["prettier", "--write"]],
    }

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
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: Path not found: {path}"

        ext = path.suffix.lower() if path.is_file() else ".py"

        if formatter:
            formatter_cmd = [formatter, str(path)]
        else:
            formatter_cmd = self._find_formatter(ext)

        if not formatter_cmd:
            return f"No formatter found for extension: {ext}"

        cmd = formatter_cmd + [str(path)]
        result = self._run_command(cmd, timeout=120)

        output_parts = [f"Formatter: {formatter_cmd[0]}"]
        output_parts.append(f"Path: {path}")

        if result.returncode == 0:
            output_parts.append("Formatted successfully!")
        else:
            output_parts.append(f"Exit code: {result.returncode}")
            if result.stderr:
                output_parts.append(f"Errors:\n{result.stderr.strip()}")

        return "\n".join(output_parts)

    def _find_formatter(self, ext: str) -> list[str] | None:
        """Find an available formatter for the extension."""
        import shutil

        formatters = self._FORMATTER_MAP.get(ext, [])
        for fmt_cmd in formatters:
            if shutil.which(fmt_cmd[0]):
                return list(fmt_cmd)
        return None
