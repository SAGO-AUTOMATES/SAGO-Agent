"""Call-graph extraction for Python codebases.

Builds caller -> callee edges using the standard library ``ast`` module. This is
an additive, opt-in helper used by code-intelligence features; it does not
replace the existing symbol graph.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("sago.memory.call_graph")


@dataclass
class CallEdge:
    caller: str
    callee: str
    line: int = 0


@dataclass
class CallGraph:
    edges: list[CallEdge] = field(default_factory=list)
    callers: dict[str, list[str]] = field(default_factory=dict)
    callees: dict[str, list[str]] = field(default_factory=dict)

    def add(self, caller: str, callee: str, line: int = 0) -> None:
        self.edges.append(CallEdge(caller=caller, callee=callee, line=line))
        self.callers.setdefault(caller, []).append(callee)
        self.callees.setdefault(callee, []).append(caller)


class PythonCallGraphExtractor:
    """Extract call edges from Python source files."""

    def extract_file(self, file_path: Path, content: str | None = None) -> CallGraph:
        graph = CallGraph()
        try:
            if content is None:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            return graph

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                caller = node.name
                for child in ast.walk(node):
                    if child is node:
                        continue
                    if isinstance(child, ast.Call):
                        callee = self._call_name(child.func)
                        if callee:
                            graph.add(caller, callee, getattr(child, "lineno", 0))
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

    def extract_directory(self, root_dir: str | Path) -> CallGraph:
        merged = CallGraph()
        root = Path(root_dir)
        for path in root.rglob("*.py"):
            if any(part in {".git", "__pycache__", ".venv", "venv"} for part in path.parts):
                continue
            try:
                g = self.extract_file(path)
            except Exception as e:
                logger.debug("Call graph extraction failed for %s: %s", path, e)
                continue
            for edge in g.edges:
                merged.add(edge.caller, edge.callee, edge.line)
        return merged


def get_call_graph(root_dir: str | Path | None = None) -> CallGraph:
    extractor = PythonCallGraphExtractor()
    if root_dir is None:
        return CallGraph()
    return extractor.extract_directory(root_dir)
