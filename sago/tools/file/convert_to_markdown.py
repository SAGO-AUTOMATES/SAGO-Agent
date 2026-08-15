"""Convert to Markdown Tool - Convert office docs, PDFs, spreadsheets, and web files to Markdown.

Powered by MarkItDown with graceful fallbacks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.utils.markitdown_converter import convert_file_to_markdown, is_markitdown_available


class ConvertToMarkdownArgs(BaseModel):
    """Arguments for ConvertToMarkdownTool."""

    file_path: str = Field(
        description="Path to the document, PDF, spreadsheet, presentation, or web file to convert"
    )
    output_path: str = Field(
        default="",
        description="Optional file path to save the resulting Markdown file to",
    )


class ConvertToMarkdownTool(BaseTool):
    """Tool for converting complex file formats into clean, token-efficient Markdown."""

    name = "convert_to_markdown"
    description = (
        "Convert documents (PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON, XML, etc.) "
        "into clean, token-efficient Markdown using MarkItDown."
    )
    args_model = ConvertToMarkdownArgs

    def _run(
        self,
        file_path: str,
        output_path: str = "",
        **kwargs: Any,
    ) -> str:
        """Convert a file to Markdown.

        Args:
            file_path: Path to the input file.
            output_path: Optional path to save converted Markdown to.

        Returns:
            Converted Markdown string or confirmation message if saved to file.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a regular file: {path}"

        success, content = convert_file_to_markdown(path)
        if not success:
            avail_msg = (
                ""
                if is_markitdown_available()
                else "\nTip: Run `pip install markitdown` to enable full parsing for all Office and PDF formats."
            )
            return f"Error converting '{path.name}' to markdown: {content}{avail_msg}"

        if output_path:
            out = self._expand_path(output_path)
            try:
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(content, encoding="utf-8")
                return f"Successfully converted '{path.name}' and saved markdown to '{out}' ({len(content)} chars)."
            except Exception as e:
                return f"Error saving markdown to '{output_path}': {e}\n\nConverted Content Preview:\n{content[:2000]}"

        return content
