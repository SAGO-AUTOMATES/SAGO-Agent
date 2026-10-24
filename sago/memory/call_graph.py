"""Call-graph extraction for Python and multi-language codebases.

Builds caller -> callee edges using AST and tree-sitter/regex parsers.
Provides 2-hop neighborhood expansion for graph-guided context assembly.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("sago.memory.call_graph")


@dataclass
class CallEdge:
    caller: str
    callee: str
    line: int = 0
    file_path: str = ""


@dataclass
class CallGraph:
    edges: list[CallEdge] = field(default_factory=list)
    callers: dict[str, list[str]] = field(default_factory=dict)  # caller -> list of callees
    callees: dict[str, list[str]] = field(default_factory=dict)  # callee -> list of callers
    symbol_files: dict[str, str] = field(default_factory=dict)  # symbol -> file_path

    def add(self, caller: str, callee: str, line: int = 0, file_path: str = "") -> None:
        if not caller or not callee or caller == callee:
            return
        self.edges.append(CallEdge(caller=caller, callee=callee, line=line, file_path=file_path))
        if callee not in self.callers.setdefault(caller, []):
            self.callers[caller].append(callee)
        if caller not in self.callees.setdefault(callee, []):
            self.callees[callee].append(caller)
        if file_path:
            self.symbol_files[caller] = file_path

    def get_callees(self, caller: str) -> list[str]:
        """Return list of symbols called by `caller`."""
        return self.callers.get(caller, [])

    def get_callers(self, callee: str) -> list[str]:
        """Return list of symbols that call `callee`."""
        return self.callees.get(callee, [])

    def get_n_hop_neighborhood(
        self, seed_symbols: list[str], max_hops: int = 2
    ) -> dict[int, list[tuple[str, str, str]]]:
        """Compute the n-hop call-graph neighborhood from seed symbols.

        Returns {hop: [(source, relation, target)]} where relation is 'calls' or 'called_by'.
        """
        neighborhood: dict[int, list[tuple[str, str, str]]] = {
            h: [] for h in range(1, max_hops + 1)
        }
        visited_symbols = set(seed_symbols)
        current_frontier = set(seed_symbols)

        for hop in range(1, max_hops + 1):
            next_frontier: set[str] = set()
            for sym in current_frontier:
                # Direct callees (sym calls target)
                for callee in self.get_callees(sym):
                    if callee not in visited_symbols:
                        neighborhood[hop].append((sym, "calls", callee))
                        next_frontier.add(callee)

                # Direct callers (caller calls sym)
                for caller in self.get_callers(sym):
                    if caller not in visited_symbols:
                        neighborhood[hop].append((caller, "calls", sym))
                        next_frontier.add(caller)

            visited_symbols.update(next_frontier)
            current_frontier = next_frontier
            if not current_frontier:
                break

        return neighborhood


class PythonCallGraphExtractor:
    """Extract call edges from Python source files."""

    def extract_file(self, file_path: Path, content: str | None = None) -> CallGraph:
        graph = CallGraph()
        try:
            if content is None:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, Exception):
            return graph

        str_fp = str(file_path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = node.name
                for child in ast.walk(node):
                    if child is node:
                        continue
                    if isinstance(child, ast.Call):
                        callee = self._call_name(child.func)
                        if callee:
                            graph.add(caller, callee, getattr(child, "lineno", 0), str_fp)
        return graph

    @staticmethod
    def _call_name(func: ast.AST) -> str:
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        if isinstance(func, ast.Call):
            return PythonCallGraphExtractor._call_name(func.func)
        return ""


class MultiLanguageCallGraphExtractor:
    """Extract call edges across Python, JS/TS, Go, Rust, Java, and C/C++ files."""

    PYTHON_EXTRACTOR = PythonCallGraphExtractor()

    CALL_PATTERNS = [
        # Call pattern: identifier followed by '('
        re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\("),
    ]

    FUNC_DEF_PATTERNS = [
        # Rust
        re.compile(r"^(?:pub\s+)?(?:async\s+)?fn\s+([a-zA-Z0-9_]+)"),
        # Go
        re.compile(r"^func\s+(?:\([^)]+\)\s+)?([a-zA-Z0-9_]+)"),
        # JS/TS
        re.compile(r"^(?:export\s+)?(?:async\s+)?function\s+([a-zA-Z0-9_]+)"),
        re.compile(r"^(?:const|let)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"),
        # Java / C / C++
        re.compile(
            r"^(?:public|protected|private)?\s*(?:static\s+)?[a-zA-Z0-9_<>[\]]+\s+([a-zA-Z0-9_]+)\s*\("
        ),
    ]

    def extract_file(self, file_path: Path, content: str | None = None) -> CallGraph:
        ext = file_path.suffix.lower()
        if ext == ".py":
            return self.PYTHON_EXTRACTOR.extract_file(file_path, content)

        graph = CallGraph()
        try:
            if content is None:
                content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return graph

        str_fp = str(file_path)
        lines = content.splitlines()
        current_func: str | None = None

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Detect function definition
            matched_fn = None
            for pat in self.FUNC_DEF_PATTERNS:
                m = pat.search(stripped)
                if m:
                    matched_fn = m.group(1)
                    break

            if matched_fn and matched_fn not in ("if", "for", "while", "switch", "catch"):
                current_func = matched_fn
                continue

            if current_func:
                # Find calls inside current function
                for m in self.CALL_PATTERNS[0].finditer(stripped):
                    callee = m.group(1)
                    if callee not in (
                        "if",
                        "for",
                        "while",
                        "switch",
                        "catch",
                        "return",
                        "sizeof",
                        "typeof",
                    ):
                        graph.add(current_func, callee, idx, str_fp)

        return graph

    def extract_directory(self, root_dir: str | Path, max_files: int = 500) -> CallGraph:
        merged = CallGraph()
        root = Path(root_dir)
        supported_exts = {".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp"}
        ignore_dirs = {
            ".git",
            "__pycache__",
            ".venv",
            "venv",
            "node_modules",
            "target",
            "vendor",
            "dist",
            "build",
        }

        count = 0
        for root_path, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
            for f in files:
                p = Path(root_path) / f
                if p.suffix.lower() in supported_exts:
                    try:
                        g = self.extract_file(p)
                        for edge in g.edges:
                            merged.add(edge.caller, edge.callee, edge.line, edge.file_path)
                        count += 1
                        if count >= max_files:
                            break
                    except Exception as e:
                        logger.debug("Call graph extraction failed for %s: %s", p, e)
            if count >= max_files:
                break

        return merged


_CACHED_GRAPH: CallGraph | None = None
_CACHED_ROOT: str | None = None


def get_call_graph(root_dir: str | Path | None = None) -> CallGraph:
    """Retrieve or build call graph for directory."""
    global _CACHED_GRAPH, _CACHED_ROOT
    if root_dir is None:
        return CallGraph()

    root_str = str(Path(root_dir).resolve())
    if _CACHED_GRAPH is not None and _CACHED_ROOT == root_str:
        return _CACHED_GRAPH

    extractor = MultiLanguageCallGraphExtractor()
    _CACHED_GRAPH = extractor.extract_directory(root_str)
    _CACHED_ROOT = root_str
    return _CACHED_GRAPH
