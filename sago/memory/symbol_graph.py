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

        def _extract_class(node: ast.ClassDef, depth: int = 0) -> SymbolInfo:
            """Recursively extract class symbols including nested classes."""
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
                    # Detect decorator type
                    decorators = []
                    for d in item.decorator_list:
                        if hasattr(ast, "unparse"):
                            decorators.append(ast.unparse(d))
                    decorator_names = [d.lower() for d in decorators]

                    if any(
                        "property" in d and "setter" not in d and "deleter" not in d
                        for d in decorator_names
                    ):
                        m_type = "property"
                    elif "staticmethod" in decorator_names:
                        m_type = "staticmethod"
                    elif "classmethod" in decorator_names:
                        m_type = "classmethod"
                    elif isinstance(item, ast.AsyncFunctionDef):
                        m_type = "async_method"
                    else:
                        m_type = "method"

                    # Include type annotations in signature
                    args = []
                    for a in item.args.args:
                        arg_str = a.arg
                        if a.annotation and hasattr(ast, "unparse"):
                            arg_str += f": {ast.unparse(a.annotation)}"
                        args.append(arg_str)
                    if item.args.vararg and hasattr(ast, "unparse"):
                        args.append(f"*{item.args.vararg.arg}")
                    if item.args.kwarg and hasattr(ast, "unparse"):
                        args.append(f"**{item.args.kwarg.arg}")
                    sig = ", ".join(args)
                    m_doc = ast.get_docstring(item) or ""
                    class_sym.children.append(
                        SymbolInfo(
                            name=item.name,
                            symbol_type=m_type,
                            line_number=item.lineno,
                            signature=sig,
                            docstring=m_doc,
                        )
                    )
                elif isinstance(item, ast.ClassDef):
                    # Nested class support
                    class_sym.children.append(_extract_class(item, depth + 1))
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    # @dataclass field support
                    ann = ast.unparse(item.annotation) if hasattr(ast, "unparse") else ""
                    default = ""
                    if item.value and hasattr(ast, "unparse"):
                        default = f" = {ast.unparse(item.value)}"
                    class_sym.children.append(
                        SymbolInfo(
                            name=item.target.id,
                            symbol_type="field",
                            line_number=item.lineno,
                            signature=f"{ann}{default}",
                        )
                    )

            return class_sym

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
                args = []
                for a in node.args.args:
                    arg_str = a.arg
                    if a.annotation and hasattr(ast, "unparse"):
                        arg_str += f": {ast.unparse(a.annotation)}"
                    args.append(arg_str)
                if node.args.vararg and hasattr(ast, "unparse"):
                    args.append(f"*{node.args.vararg.arg}")
                if node.args.kwarg and hasattr(ast, "unparse"):
                    args.append(f"**{node.args.kwarg.arg}")
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
                symbols.append(_extract_class(node))

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
        """Regex-based symbol extractor for JS/TS/Go/Rust/Java/C++/Ruby/PHP/Kotlin/Swift/C#/Dart/Elixir/Lua."""
        symbols: list[SymbolInfo] = []
        lines = content.splitlines()

        # Comprehensive high-precision patterns across languages
        patterns = [
            # JS/TS patterns
            (r"^(?:export\s+)?(?:default\s+)?class\s+([A-Za-z0-9_]+)", "class"),
            (r"^(?:export\s+)?interface\s+([A-Za-z0-9_]+)", "interface"),
            (r"^(?:export\s+)?(?:type|enum)\s+([A-Za-z0-9_]+)", "type"),
            (r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),
            (r"^(?:const|let)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>", "function"),
            # Rust patterns
            (r"^(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)\s*(?:<.*?>)?\s*\((.*?)\)", "function"),
            (r"^(?:pub\s+)?(?:struct|enum|union)\s+([A-Za-z0-9_]+)", "type"),
            (r"^(?:pub\s+)?trait\s+([A-Za-z0-9_]+)", "interface"),
            (r"^impl(?:\s*<.*?>)?\s+([A-Za-z0-9_]+)", "impl"),
            # Go patterns
            (r"^type\s+([A-Za-z0-9_]+)\s+struct", "class"),
            (r"^type\s+([A-Za-z0-9_]+)\s+interface", "interface"),
            (r"^func\s+(?:\(.*?\)\s+)?([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),
            # C/C++/Java patterns
            (r"^(?:public|private|protected)?\s*(?:static)?\s*class\s+([A-Za-z0-9_]+)", "class"),
            (r"^(?:struct|class)\s+([A-Za-z0-9_]+)\s*\{?", "class"),
            # Ruby patterns
            (r"^class\s+([A-Za-z0-9_:]+)", "class"),
            (r"^module\s+([A-Za-z0-9_:]+)", "module"),
            (r"^(?:def|define_method)\s+([A-Za-z0-9_?!]+)\s*(?:\((.*?)\))?", "function"),
            # PHP patterns
            (r"^(?:abstract\s+)?class\s+(\w+)", "class"),
            (r"^interface\s+(\w+)", "interface"),
            (r"^trait\s+(\w+)", "interface"),
            (
                r"^(?:public|protected|private)\s+(?:static\s+)?function\s+(\w+)\s*\((.*?)\)",
                "function",
            ),
            # Kotlin patterns
            (r"^(?:data\s+)?class\s+(\w+)", "class"),
            (r"^interface\s+(\w+)", "interface"),
            (r"^object\s+(\w+)", "class"),
            (r"^(?:fun|suspend\s+fun)\s+(\w+)\s*\((.*?)\)", "function"),
            # Swift patterns
            (r"^class\s+(\w+)", "class"),
            (r"^struct\s+(\w+)", "class"),
            (r"^protocol\s+(\w+)", "interface"),
            (r"^enum\s+(\w+)", "type"),
            (r"^(?:func|init)\s+(?:<.*?>)?\s*(\w+)\s*\((.*?)\)", "function"),
            # C# patterns
            (r"^(?:public|private|protected|internal)?\s*(?:partial\s+)?class\s+(\w+)", "class"),
            (r"^interface\s+(\w+)", "interface"),
            (r"^enum\s+(\w+)", "type"),
            (
                r"^(?:public|private|protected)\s+(?:static\s+)?(?:async\s+)?(\w+)\s+(\w+)\s*\((.*?)\)",
                "function",
            ),
            # Dart patterns
            (r"^(?:abstract\s+)?class\s+(\w+)", "class"),
            (r"^(?:mixin)\s+(\w+)", "interface"),
            (
                r"^(?:void|int|String|bool|double|Future|Stream|List|Map)?\s*(\w+)\s*\((.*?)\)\s*(?:async\s*)?\{?",
                "function",
            ),
            # Elixir patterns
            (r"^(?:defmodule|defprotocol)\s+([A-Za-z0-9_.]+)", "class"),
            (r"^def(?:p)?\s+(\w+)(?:\((.*?)\))?", "function"),
            (r"^(?:defmacro|defmacrop)\s+(\w+)(?:\((.*?)\))?", "function"),
            # Lua patterns
            (r"^function\s+([A-Za-z0-9_.:]+)\s*\((.*?)\)", "function"),
            (r"^(?:local\s+)?function\s+([A-Za-z0-9_]+)\s*\((.*?)\)", "function"),
        ]

        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            # Skip comment-only lines
            if line_str.startswith("//") or line_str.startswith("#") or line_str.startswith("--"):
                continue
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

    def extract_sql_symbols(self, file_path: Path, content: str) -> FileSymbols:
        """Regex-based symbol extractor for SQL (tables, views, functions, etc.)."""
        symbols: list[SymbolInfo] = []
        lines = content.splitlines()
        patterns = [
            (r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"]?([A-Za-z0-9_]+)", "table"),
            (
                r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?VIEW\s+[`\"]?([A-Za-z0-9_]+)",
                "view",
            ),
            (
                r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+[`\"]?([A-Za-z0-9_]+)",
                "function",
            ),
            (r"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+[`\"]?([A-Za-z0-9_]+)", "trigger"),
            (r"CREATE\s+(?:OR\s+REPLACE\s+)?INDEX\s+[`\"]?([A-Za-z0-9_]+)", "index"),
        ]
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            for pat, sym_type in patterns:
                m = re.search(pat, line_str, re.IGNORECASE)
                if m:
                    symbols.append(
                        SymbolInfo(
                            name=m.group(1),
                            symbol_type=sym_type,
                            line_number=i,
                            signature="",
                        )
                    )
                    break

        return FileSymbols(
            file_path=str(
                file_path.relative_to(self.root_dir)
                if file_path.is_relative_to(self.root_dir)
                else file_path
            ),
            language="sql",
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
            elif suffix == ".java":
                fs = self.extract_generic_symbols(file_path, content, "java")
            elif suffix in (".c", ".h"):
                fs = self.extract_generic_symbols(file_path, content, "c")
            elif suffix in (".cpp", ".hpp", ".cc", ".cxx"):
                fs = self.extract_generic_symbols(file_path, content, "cpp")
            elif suffix == ".rb":
                fs = self.extract_generic_symbols(file_path, content, "ruby")
            elif suffix == ".php":
                fs = self.extract_generic_symbols(file_path, content, "php")
            elif suffix == ".kt":
                fs = self.extract_generic_symbols(file_path, content, "kotlin")
            elif suffix == ".scala":
                fs = self.extract_generic_symbols(file_path, content, "scala")
            elif suffix == ".swift":
                fs = self.extract_generic_symbols(file_path, content, "swift")
            elif suffix == ".cs":
                fs = self.extract_generic_symbols(file_path, content, "csharp")
            elif suffix == ".dart":
                fs = self.extract_generic_symbols(file_path, content, "dart")
            elif suffix in (".ex", ".exs"):
                fs = self.extract_generic_symbols(file_path, content, "elixir")
            elif suffix == ".lua":
                fs = self.extract_generic_symbols(file_path, content, "lua")
            elif suffix == ".sql":
                fs = self.extract_sql_symbols(file_path, content)
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

    def get_symbol_outline(self, max_files: int = 100) -> dict[str, list[dict[str, object]]]:
        """Return a structured symbol outline suitable for context selection.

        This is deliberately separate from :meth:`generate_repo_map`, whose
        compact text output is intended for direct display in a prompt.
        """
        ignored_dirs = {
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
        outline: dict[str, list[dict[str, object]]] = {}
        scanned = 0

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for filename in sorted(files):
                if filename.startswith("."):
                    continue
                symbols = self.scan_file(Path(root) / filename)
                if not symbols:
                    continue
                outline[symbols.file_path] = [
                    {"name": symbol.name, "kind": symbol.symbol_type, "line": symbol.line_number}
                    for symbol in symbols.symbols
                ]
                scanned += 1
                if scanned >= max_files:
                    return outline
        return outline

    def generate_clean_tui_map(
        self,
        max_files: int = 150,
        filter_query: str | None = None,
    ) -> str:
        """Generate a clean, structured repository symbol map for TUI & LLM viewing."""
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
        total_files = 0
        total_symbols = 0
        file_sections: list[str] = []

        q = (filter_query or "").strip().lower()

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in sorted(dirs) if d not in ignore_dirs and not d.startswith(".")]
            for f in sorted(files):
                if f.startswith(".") or f.endswith(
                    (".pyc", ".min.js", ".map", ".lock", ".png", ".jpg", ".ico", ".svg")
                ):
                    continue
                file_path = Path(root) / f
                fs = self.scan_file(file_path)
                if not fs or not fs.symbols:
                    continue

                # Filter matching
                if q:
                    path_match = q in fs.file_path.lower()
                    matching_syms = [
                        s
                        for s in fs.symbols
                        if q in s.name.lower() or any(q in c.name.lower() for c in s.children)
                    ]
                    if not path_match and not matching_syms:
                        continue
                    active_symbols = fs.symbols if path_match else matching_syms
                else:
                    active_symbols = fs.symbols

                total_files += 1
                total_symbols += len(active_symbols)

                lines = [f"📂 **`{fs.file_path}`** `({fs.line_count} lines)`"]
                for sym in active_symbols[:15]:
                    kind_icon = "🔷" if sym.symbol_type == "class" else "⚡"
                    sig = f"({sym.signature})" if sym.signature else ""
                    doc_snippet = (
                        f" — *{sym.docstring.strip().splitlines()[0][:45]}*"
                        if sym.docstring
                        else ""
                    )
                    lines.append(f"  {kind_icon} `{sym.name}{sig}`{doc_snippet}")
                    for child in sym.children[:6]:
                        child_sig = f"({child.signature})" if child.signature else ""
                        lines.append(f"    └─ 🔹 `{child.name}{child_sig}`")
                    if len(sym.children) > 6:
                        lines.append(f"    └─ *... and {len(sym.children) - 6} more methods*")

                if len(active_symbols) > 15:
                    lines.append(f"  *... and {len(active_symbols) - 15} more symbols*")

                file_sections.append("\n".join(lines))
                if total_files >= max_files:
                    break
            if total_files >= max_files:
                break

        if not file_sections:
            if q:
                return f"🔍 **No symbols or files found matching:** `{filter_query}`\n*Try `/map` without filters to inspect all symbols.*"
            return "📂 **No source code files or symbols found in current directory.**"

        filter_note = f" (Filter: `{filter_query}`)" if q else ""
        header = (
            f"### 🗺️ Repository Symbol Map: `{self.root_dir.name}`{filter_note}\n"
            f"📊 **Overview**: `{total_files}` Files │ `{total_symbols}` Core Symbols\n\n"
            "---\n"
        )
        body = "\n\n".join(file_sections)
        footer = "\n\n---\n*Tip: Run `/map <query>` to search specific symbols, or `/graph` for architecture diagrams.*"
        return header + body + footer
