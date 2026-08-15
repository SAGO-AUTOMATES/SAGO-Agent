"""Read File Tool - Read the contents of a file.

Cross-platform file reading with encoding detection.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ReadFileArgs(BaseModel):
    """Arguments for ReadFileTool."""

    file_path: str = Field(description="Path to the file to read")
    encoding: str = Field(default="utf-8", description="File encoding (default: utf-8)")
    offset: int = Field(default=0, description="Line number to start reading from (0-indexed)")
    limit: int = Field(default=0, description="Maximum number of lines to read (0=all)")


class ReadFileTool(BaseTool):
    """Tool for reading file contents."""

    name = "read_file"
    description = "Read the contents of a file. Returns the file content as a string."
    args_model = ReadFileArgs

    def _run(
        self,
        file_path: str,
        encoding: str = "utf-8",
        offset: int = 0,
        limit: int = 0,
        **kwargs: Any,
    ) -> str:
        """Read a file's contents.

        Args:
            file_path: Path to the file to read.
            encoding: File encoding.
            offset: Line number to start from (0-indexed).
            limit: Maximum lines to read (0=all).

        Returns:
            File contents as a string.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        from sago.utils.markitdown_converter import convert_file_to_markdown, is_document_file

        # Check if the file is a document format best parsed via MarkItDown
        if is_document_file(path):
            success, md_content = convert_file_to_markdown(path)
            if success:
                lines = md_content.splitlines(keepends=True)
                if offset > 0:
                    lines = lines[offset:]
                if limit > 0:
                    lines = lines[:limit]
                result = "".join(lines)
                line_count = len(lines)
                total_lines = len(md_content.splitlines())
                if line_count == 0:
                    header = f"--- {path} (converted to Markdown, empty or beyond offset, total lines: {total_lines}) ---\n"
                else:
                    header = f"--- {path} (converted to Markdown, lines {offset + 1}-{offset + line_count} of {total_lines}) ---\n"
                return header + result

        try:
            content = path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            # Try MarkItDown first on decode failure before latin-1
            success, md_content = convert_file_to_markdown(path)
            if success:
                lines = md_content.splitlines(keepends=True)
                if offset > 0:
                    lines = lines[offset:]
                if limit > 0:
                    lines = lines[:limit]
                result = "".join(lines)
                line_count = len(lines)
                total_lines = len(md_content.splitlines())
                if line_count == 0:
                    header = f"--- {path} (converted to Markdown, empty or beyond offset, total lines: {total_lines}) ---\n"
                else:
                    header = f"--- {path} (converted to Markdown, lines {offset + 1}-{offset + line_count} of {total_lines}) ---\n"
                return header + result

            # Try with latin-1 as fallback
            try:
                content = path.read_text(encoding="latin-1")
            except Exception as e:
                return f"Error: Could not read file with any encoding: {e}"

        lines = content.splitlines(keepends=True)

        if offset > 0:
            lines = lines[offset:]
        if limit > 0:
            lines = lines[:limit]

        result = "".join(lines)
        line_count = len(lines)
        total_lines = len(content.splitlines())

        if line_count == 0:
            header = f"--- {path} (empty or beyond offset, total lines: {total_lines}) ---\n"
        else:
            header = f"--- {path} (lines {offset + 1}-{offset + line_count} of {total_lines}) ---\n"
        return header + result
