"""Symbol Graph & Repo Map Engine - Scalable symbol extraction for 1,000+ file codebases.

Extracts symbols (classes, functions, methods, types, exports, docstrings) across
multiple languages without bloating the LLM context window.
"""

from __future__ import annotations

import ast
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SymbolInfo:
    """Extracted code symbol."""

    name: str
    symbol_type: str  # "class", "function", "async_function", "method", "interface", "type"
    line_number: int
    signature: str = ""
    docstring: str = ""
    children: list[SymbolInfo] = field(default_factory=list)

    def to_compact_str(self, indent: int = 0) -> str:
        prefix = "  " * indent
        sig = f"({self.signature})" if self.signature else ""
        res = f"{prefix}{self.symbol_type} {self.name}{sig}"
        if self.docstring:
            first_line = self.docstring.strip().splitlines()[0][:60]
            res += f"  # {first_line}"
        for child in self.children:
            res += "\n" + child.to_compact_str(indent + 1)
        return res


@dataclass
class FileSymbols:
    """Symbol outline for a single file."""

    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    line_count: int = 0
    size_bytes: int = 0
    mtime: float = 0.0

    def to_compact_outline(self) -> str:
        if not self.symbols:
            return f"{self.file_path} ({self.line_count} lines)"
        header = f"{self.file_path} ({self.line_count} lines):"
        sym_lines = [s.to_compact_str(indent=1) for s in self.symbols]
        return header + "\n" + "\n".join(sym_lines)


class SymbolGraph:
    """In-memory symbol graph with AST parsers and caching."""

    def __init__(self, root_dir: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir) if root_dir else Path.cwd()
        self._cache: dict[str, FileSymbols] = {}

    def extract_python_symbols(self, file_path: Path, content: str) -> FileSymbols:
        """Parse Python AST to extract classes, methods, and functions with signatures."""
        symbols: list[SymbolInfo] = []
        imports: list[str] = []

        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return FileSymbols(
                file_path=str(file_path),
                language="python",
                line_count=len(content.splitlines()),
                size_bytes=len(content),
            )

        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                else:
                    mod = node.module or ""
                    for alias in node.names:
                        imports.append(f"{mod}.{alias.name}")

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sym_type = (
                    "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                )
                args = [a.arg for a in node.args.args]
                sig = ", ".join(args)
                doc = ast.get_docstring(node) or ""
                symbols.append(
                    SymbolInfo(
                        name=node.name,
                        symbol_type=sym_type,
                        line_number=node.lineno,
                        signature=sig,
                        docstring=doc,
                    )
                )

            elif isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                bases = [ast.unparse(b) for b in node.bases if hasattr(ast, "unparse")]
                base_str = f"({', '.join(bases)})" if bases else ""
                class_sym = SymbolInfo(
                    name=node.name + base_str,
                    symbol_type="class",
                    line_number=node.lineno,
                    docstring=doc,
                )

                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m_type = (
                            "async_method" if isinstance(item, ast.AsyncFunctionDef) else "method"
                        )
                        m_args = [a.arg for a in item.args.args]
                        m_sig = ", ".join(m_args)
                        m_doc = ast.get_docstring(item) or ""
                        class_sym.children.append(
                            SymbolInfo(
                                name=item.name,
                                symbol_type=m_type,
                                line_number=item.lineno,
                                signature=m_sig,
                                docstring=m_doc,
                            )
                        )
                symbols.append(class_sym)

        return FileSymbols(
            file_path=str(
                file_path.relative_to(self.root_dir)
                if file_path.is_relative_to(self.root_dir)
                else file_path
            ),
            language="python",
            symbols=symbols,
            imports=imports,
            line_count=len(content.splitlines()),
            size_bytes=len(content),
            mtime=file_path.stat().st_mtime if file_path.exists() else time.time(),
        )

    def extract_generic_symbols(self, file_path: Path, content: str, lang: str) -> FileSymbols:
        """Regex-based symbol extractor for JS/TS/Go/Rust/Java/C++."""
        symbols: list[SymbolInfo] = []
        lines = content.splitlines()

        # Simple high-precision patterns
        patterns = [
            (r"^(?:export\s+)?class\s+([A-Za-z0-9_]+)", "class"),
            (r"^(?:export\s+)?interface\s+([A-Za-z0-9_]+)", "interface"),
            (r"^(?:export\s+)?type\s+([A-Za-z0-9_]+)", "type"),
            (r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),
            (r"^(?:pub\s+)?fn\s+([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),  # Rust
            (r"^func\s+(?:\(.*?\)\s+)?([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),  # Go
        ]

        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            for pat, sym_type in patterns:
                m = re.search(pat, line_str)
                if m:
                    name = m.group(1)
                    sig = m.group(2) if len(m.groups()) > 1 else ""
                    symbols.append(
                        SymbolInfo(
                            name=name,
                            symbol_type=sym_type,
                            line_number=i,
                            signature=sig,
                        )
                    )
                    break

        return FileSymbols(
            file_path=str(
                file_path.relative_to(self.root_dir)
                if file_path.is_relative_to(self.root_dir)
                else file_path
            ),
            language=lang,
            symbols=symbols,
            line_count=len(lines),
            size_bytes=len(content),
            mtime=file_path.stat().st_mtime if file_path.exists() else time.time(),
        )

    def scan_file(self, file_path: Path) -> FileSymbols | None:
        """Scan a single file with modification timestamp caching."""
        str_path = str(file_path)
        try:
            mtime = file_path.stat().st_mtime
            if str_path in self._cache and self._cache[str_path].mtime == mtime:
                return self._cache[str_path]

            content = file_path.read_text(encoding="utf-8", errors="replace")
            suffix = file_path.suffix.lower()

            if suffix == ".py":
                fs = self.extract_python_symbols(file_path, content)
            elif suffix in (".ts", ".tsx", ".js", ".jsx"):
                fs = self.extract_generic_symbols(file_path, content, "typescript")
            elif suffix == ".rs":
                fs = self.extract_generic_symbols(file_path, content, "rust")
            elif suffix == ".go":
                fs = self.extract_generic_symbols(file_path, content, "go")
            else:
                fs = FileSymbols(
                    file_path=str(
                        file_path.relative_to(self.root_dir)
                        if file_path.is_relative_to(self.root_dir)
                        else file_path
                    ),
                    language="other",
                    line_count=len(content.splitlines()),
                    size_bytes=len(content),
                    mtime=mtime,
                )

            self._cache[str_path] = fs
            return fs
        except Exception:
            return None

    def generate_repo_map(
        self,
        max_files: int = 1000,
        max_tokens: int = 4000,
        filter_query: str | None = None,
    ) -> str:
        """Generate a compact, token-efficient repository symbol map."""
        ignore_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".venv",
            "venv",
            "dist",
            "build",
            ".pytest_cache",
            ".ruff_cache",
            ".next",
            ".cache",
            "target",
            "vendor",
        }
        all_outlines: list[str] = []
        count = 0

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for f in sorted(files):
                if f.startswith(".") or f.endswith(
                    (".pyc", ".min.js", ".map", ".lock", ".png", ".jpg", ".ico")
                ):
                    continue
                file_path = Path(root) / f
                fs = self.scan_file(file_path)
                if fs:
                    if filter_query and filter_query.lower() not in fs.file_path.lower():
                        # Check if symbol matches
                        has_sym_match = any(
                            filter_query.lower() in s.name.lower() for s in fs.symbols
                        )
                        if not has_sym_match:
                            continue

                    all_outlines.append(fs.to_compact_outline())
                    count += 1
                    if count >= max_files:
                        break
            if count >= max_files:
                break

        full_map = "\n\n".join(all_outlines)
        # Token estimation & trimming
        if len(full_map) > max_tokens * 4:
            full_map = full_map[: max_tokens * 4] + "\n\n... [Repo map truncated for brevity]"
        return full_map
