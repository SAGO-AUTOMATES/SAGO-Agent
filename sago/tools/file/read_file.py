"""Read File Tool - Read the contents of a file.

Cross-platform file reading with encoding detection, AST-aware structure extraction,
binary detection, and smart size handling.
"""

from __future__ import annotations

import ast
import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.file.read_file")


class ReadFileArgs(BaseModel):
    """Arguments for ReadFileTool."""

    file_path: str = Field(description="Path to the file to read")
    encoding: str = Field(default="utf-8", description="File encoding (default: utf-8)")
    offset: int = Field(default=0, description="Line number to start reading from (0-indexed)")
    limit: int = Field(default=0, description="Maximum number of lines to read (0=all)")
    with_structure: bool = Field(
        default=False, description="If true, include AST structure summary for code files"
    )


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
        with_structure: bool = False,
        **kwargs: Any,
    ) -> str:
        """Read a file's contents with smart detection.

        Features:
        - Binary detection (null bytes)
        - Large-file warning & truncation hint
        - Document conversion via MarkItDown
        - AST parsing for Python (syntax check + structure summary when requested or for large files)
        - Encoding fallback

        Args:
            file_path: Path to the file to read.
            encoding: File encoding.
            offset: Line number to start from (0-indexed).
            limit: Maximum lines to read (0=all).
            with_structure: Include AST structure summary.

        Returns:
            File contents as a string.
        """
        logger.debug(
            "read_file called: path=%s, encoding=%s, offset=%d, limit=%d, with_structure=%s",
            file_path,
            encoding,
            offset,
            limit,
            with_structure,
        )
        path = self._expand_path(file_path)
        logger.debug("Resolved path: %s -> %s", file_path, path)

        if not path.exists():
            logger.warning("File not found: %s", path)
            return f"Error: File not found: {path}"
        if not path.is_file():
            logger.warning("Not a file: %s", path)
            return f"Error: Not a file: {path}"

        # Binary detection: check for null bytes in first 8KB
        logger.debug("Performing binary detection on %s", path)
        try:
            with path.open("rb") as f:
                chunk = f.read(8192)
                if b"\x00" in chunk:
                    size = path.stat().st_size
                    logger.warning("Binary file detected: %s (%d bytes)", path, size)
                    return (
                        f"Error: Binary file detected: {path} ({size} bytes). "
                        f"Use hash_checksum or appropriate binary tool instead of read_file."
                    )
        except Exception as e:
            logger.debug("Binary detection check failed: %s", e)

        # Large file warning: >500KB or >5000 lines
        try:
            size = path.stat().st_size
            if size > 500 * 1024:
                logger.warning("Large file detected: %s (%d bytes)", path, size)
                # Still allow reading but add warning in header
                pass
        except Exception:
            size = 0

        from sago.utils.markitdown_converter import convert_file_to_markdown, is_document_file

        # Check if the file is a document format best parsed via MarkItDown
        logger.debug("Checking document format for %s", path)
        if is_document_file(path):
            logger.info("Document file detected, converting to Markdown: %s", path)
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
            logger.debug("Reading file with encoding=%s: %s", encoding, path)
            content = path.read_text(encoding=encoding)
            logger.debug("Read %d bytes from %s", len(content), path)
        except UnicodeDecodeError:
            logger.warning(
                "Encoding %s failed for %s, trying MarkItDown and latin-1 fallback", encoding, path
            )
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
                logger.debug("Attempting latin-1 fallback for %s", path)
                content = path.read_text(encoding="latin-1")
                logger.info("Successfully read with latin-1 fallback: %s", path)
            except Exception as e:
                logger.error("All encoding attempts failed for %s: %s", path, e)
                return f"Error: Could not read file with any encoding: {e}"

        # Smart: AST parsing for Python files - syntax validation + optional structure
        ast_summary = ""
        if path.suffix.lower() == ".py":
            logger.debug("Parsing Python AST for %s", path)
            try:
                tree = ast.parse(content, filename=str(path))
                # Syntax OK - optionally build structure summary
                if with_structure or len(content.splitlines()) > 300:
                    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
                    funcs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
                    imports = [
                        n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))
                    ]
                    ast_summary = (
                        f"\n[AST] Python structure: {len(classes)} classes, "
                        f"{len(funcs)} functions, {len(imports)} imports"
                    )
                    logger.info(
                        "AST parsed %s: %d classes, %d functions, %d imports",
                        path,
                        len(classes),
                        len(funcs),
                        len(imports),
                    )
                    if with_structure:
                        details = []
                        for cls in classes[:10]:
                            details.append(f"  class {cls.name} (line {cls.lineno})")
                        for fn in funcs[:15]:
                            details.append(f"  def {fn.name} (line {fn.lineno})")
                        if details:
                            ast_summary += "\n" + "\n".join(details)
            except SyntaxError as e:
                ast_summary = f"\n[AST] SyntaxError at line {e.lineno}: {e.msg}"
                logger.warning("Python syntax error in %s at line %d: %s", path, e.lineno, e.msg)
            except Exception as e:
                logger.debug("AST parsing failed for %s: %s", path, e)

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

        # Add size warning for large files
        size_hint = ""
        if size > 500 * 1024 and limit == 0 and offset == 0:
            size_hint = f"[Hint] Large file ({size} bytes, {total_lines} lines) — consider using offset/limit or grep_content for targeted reads.\n"

        # Truncate extremely long output (>100KB) hint
        if len(result) > 100 * 1024 and limit == 0:
            # keep result but add hint; actual truncation handled by caller
            pass

        return header + size_hint + result + ast_summary
