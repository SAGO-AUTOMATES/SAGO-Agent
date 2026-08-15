"""MarkItDown document-to-markdown conversion utility for SAGO.

Converts complex, token-heavy file formats (PDF, DOCX, XLSX, PPTX, HTML, CSV,
JSON, XML, RTF, etc.) into clean, token-efficient, LLM-friendly Markdown.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Supported file extensions for document-to-markdown conversion
DOCUMENT_EXTENSIONS: set[str] = {
    ".pdf",
    ".docx",
    ".doc",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".html",
    ".htm",
    ".xml",
    ".csv",
    ".tsv",
    ".json",
    ".rtf",
    ".epub",
    ".zip",
    ".mp3",
    ".wav",
    ".m4a",
}


def is_markitdown_available() -> bool:
    """Check if the markitdown library is installed and importable."""
    try:
        import markitdown  # noqa: F401

        return True
    except ImportError:
        return False


def is_document_file(file_path: str | Path) -> bool:
    """Check if a file has a recognized document extension."""
    ext = Path(file_path).suffix.lower()
    return ext in DOCUMENT_EXTENSIONS


def convert_file_to_markdown(
    file_path: str | Path,
    enable_ocr: bool = False,
    **kwargs: Any,
) -> tuple[bool, str]:
    """Convert a document file to clean Markdown.

    Attempts to use the Microsoft `markitdown` library first. If unavailable
    or upon failure, falls back to native lightweight parsers for common formats
    (CSV, TSV, JSON, HTML, XML, text).

    Args:
        file_path: Path to the file to convert.
        enable_ocr: Whether to enable OCR if markitdown supports it.
        **kwargs: Additional parameters passed to markitdown or fallback converters.

    Returns:
        tuple[bool, str]: (success, markdown_content_or_error_message)
    """
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        return False, f"File not found: {path}"
    if not path.is_file():
        return False, f"Path is not a regular file: {path}"

    ext = path.suffix.lower()

    # 1. Primary: Use markitdown library if available
    if is_markitdown_available():
        try:
            from markitdown import MarkItDown

            md = MarkItDown(enable_plugins=True)
            result = md.convert(str(path))
            if result and hasattr(result, "text_content") and result.text_content:
                header = f"<!-- Converted from {path.name} via MarkItDown -->\n\n"
                return True, header + result.text_content.strip()
        except Exception as e:
            logger.warning(
                "MarkItDown conversion failed for %s (%s), trying native fallback", path, e
            )

    # 2. Fallback: Native light parsers for supported formats
    return _convert_with_fallback(path, ext)


def _convert_with_fallback(path: Path, ext: str) -> tuple[bool, str]:
    """Convert file using native Python standard library and lightweight fallbacks."""
    try:
        if ext in (".csv", ".tsv"):
            delimiter = "\t" if ext == ".tsv" else ","
            content = path.read_text(encoding="utf-8", errors="replace")
            reader = csv.reader(content.splitlines(), delimiter=delimiter)
            rows = list(reader)
            if not rows:
                return True, "_Empty CSV/TSV table._"

            lines = []
            header = rows[0]
            lines.append("| " + " | ".join(h.strip() or "-" for h in header) + " |")
            lines.append("| " + " | ".join("---" for _ in header) + " |")
            for row in rows[1:]:
                # Pad row to match header length
                padded = row + [""] * (len(header) - len(row))
                lines.append("| " + " | ".join(c.strip() for c in padded[: len(header)]) + " |")
            return True, f"<!-- Formatted from {path.name} -->\n\n" + "\n".join(lines)

        elif ext == ".json":
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw_text)
            formatted = json.dumps(data, indent=2)
            return True, f"<!-- Formatted from {path.name} -->\n\n```json\n{formatted}\n```"

        elif ext in (".html", ".htm"):
            raw_html = path.read_text(encoding="utf-8", errors="replace")
            try:
                import re

                text = re.sub(r"<script.*?</script>", "", raw_html, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<h1>(.*?)</h1>", r"# \1\n", text, flags=re.IGNORECASE)
                text = re.sub(r"<h2>(.*?)</h2>", r"## \1\n", text, flags=re.IGNORECASE)
                text = re.sub(r"<h3>(.*?)</h3>", r"### \1\n", text, flags=re.IGNORECASE)
                text = re.sub(r"<p>(.*?)</p>", r"\1\n\n", text, flags=re.IGNORECASE)
                text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
                text = re.sub(r"<[^>]+>", "", text)
                clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
                return True, f"<!-- Converted HTML from {path.name} -->\n\n" + "\n\n".join(
                    clean_lines
                )
            except Exception:
                return True, f"```html\n{raw_html[:3000]}\n```"

        elif ext in (".xml",):
            raw_xml = path.read_text(encoding="utf-8", errors="replace")
            return True, f"<!-- XML Document: {path.name} -->\n\n```xml\n{raw_xml}\n```"

        elif ext in (".txt", ".md", ".rst", ".log"):
            return True, path.read_text(encoding="utf-8", errors="replace")

        else:
            hint = (
                f"Note: Full document conversion for '{ext}' files requires the `markitdown` package.\n"
                "Install it with: `pip install markitdown`"
            )
            return (
                False,
                f"Unsupported document format '{ext}' without markitdown installed.\n{hint}",
            )

    except Exception as e:
        return False, f"Failed to parse document '{path.name}': {e}"
