"""PDF Reader Tool - Extract text from PDF files."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class PDFReaderArgs(BaseModel):
    """Arguments for PDF reading."""

    operation: str = Field(description="Operation: extract-text, info, extract-pages")
    path: str = Field(description="Path to PDF file")
    pages: str = Field(default="", description="Page range to extract (e.g., '1-5' or '1,3,5')")


class PDFReader(BaseTool):
    """Tool for reading and extracting content from PDF files."""

    name: str = "pdf_reader"
    description: str = "Read PDF files: extract text, get info, extract specific pages."
    args_model: type[BaseModel] = PDFReaderArgs

    def _run(
        self,
        operation: str,
        path: str,
        pages: str = "",
        **kwargs: Any,
    ) -> str:
        """Execute PDF operation."""
        target = self._expand_path(path)

        if not target.exists():
            return f"Error: File not found: {path}"

        if not target.suffix.lower() == ".pdf":
            return f"Error: Not a PDF file: {path}"

        try:
            # Try PyPDF2 first
            try:
                from PyPDF2 import PdfReader

                reader = PdfReader(str(target))

                if operation == "info":
                    info = reader.metadata
                    return (
                        f"PDF Info:\n"
                        f"File: {target}\n"
                        f"Pages: {len(reader.pages)}\n"
                        f"Title: {info.title if info else 'N/A'}\n"
                        f"Author: {info.author if info else 'N/A'}"
                    )

                elif operation == "extract-text":
                    text_parts = []
                    for i, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            text_parts.append(f"--- Page {i + 1} ---\n{text}")

                    full_text = "\n\n".join(text_parts)
                    return f"Extracted {len(text_parts)} pages:\n\n{full_text[:5000]}"

                elif operation == "extract-pages":
                    if not pages:
                        return "Error: pages parameter required"

                    page_indices = self._parse_page_range(pages, len(reader.pages))
                    text_parts = []
                    for i in page_indices:
                        if 0 <= i < len(reader.pages):
                            text = reader.pages[i].extract_text()
                            if text:
                                text_parts.append(f"--- Page {i + 1} ---\n{text}")

                    return (
                        f"Extracted {len(text_parts)} pages:\n\n" + "\n\n".join(text_parts)[:5000]
                    )

                else:
                    return f"Error: Invalid operation '{operation}'"

            except ImportError:
                # Fallback to pdftotext if available
                result = self._run_command(
                    f"pdftotext '{target}' -",
                    timeout=30,
                )
                if result.returncode == 0:
                    return f"PDF Text:\n{result.stdout[:5000]}"
                return "Error: PyPDF2 not installed. Run: pip install PyPDF2"

        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"

    def _parse_page_range(self, pages_str: str, total_pages: int) -> list[int]:
        """Parse page range string like '1-5' or '1,3,5'."""
        indices = []
        for part in pages_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                start = max(0, int(start) - 1)
                end = min(total_pages, int(end))
                indices.extend(range(start, end))
            else:
                idx = int(part) - 1
                if 0 <= idx < total_pages:
                    indices.append(idx)
        return sorted(set(indices))


def get_tool() -> type[PDFReader]:
    """Get the tool class."""
    return PDFReader
