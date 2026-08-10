"""AST Editor - Structure-aware code editing.

Provides intelligent code editing by understanding the structure of code,
not just text. Supports Python natively via ast module, and regex-based
structure detection for JS/TS/Go/Rust/Java/C/C++.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CodeNode:
    """A node in the code structure."""
    name: str
    node_type: str  # "function", "class", "method", "import", "variable"
    start_line: int
    end_line: int
    parent: str | None = None
    decorators: list[str] = field(default_factory=list)
    signature: str = ""
    docstring: str | None = None
    children: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.node_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent": self.parent,
            "decorators": self.decorators,
            "signature": self.signature,
        }


class ASTEditor:
    """Edit code by structure, not by text position."""

    def analyze(self, code: str, language: str = "python") -> list[CodeNode]:
        """Analyze code and return structure."""
        if language == "python":
            return self._analyze_python(code)
        elif language in ("javascript", "typescript", "js", "ts"):
            return self._analyze_js(code)
        elif language == "go":
            return self._analyze_go(code)
        elif language == "rust":
            return self._analyze_rust(code)
        elif language == "java":
            return self._analyze_java(code)
        elif language in ("c", "cpp", "c++"):
            return self._analyze_c(code)
        return []

    def _analyze_python(self, code: str) -> list[CodeNode]:
        """Analyze Python code structure using ast."""
        nodes = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return nodes

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        decorators.append(f"{ast.dump(dec.value)}.{dec.attr}")

                args = [arg.arg for arg in node.args.args]
                sig = f"def {node.name}({', '.join(args)})"
                docstring = ast.get_docstring(node)

                nodes.append(CodeNode(
                    name=node.name,
                    node_type="function",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    decorators=decorators,
                    signature=sig,
                    docstring=docstring,
                ))

            elif isinstance(node, ast.ClassDef):
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)

                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.unparse(base))

                docstring = ast.get_docstring(node)

                nodes.append(CodeNode(
                    name=node.name,
                    node_type="class",
                    start_line=node.lineno,
                    end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                    decorators=decorators,
                    signature=f"class {node.name}({', '.join(bases)})",
                    docstring=docstring,
                ))

            elif isinstance(node, ast.Import | ast.ImportFrom):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        nodes.append(CodeNode(
                            name=alias.name,
                            node_type="import",
                            start_line=node.lineno,
                            end_line=node.lineno,
                        ))
                else:
                    module = node.module or ""
                    for alias in node.names:
                        nodes.append(CodeNode(
                            name=f"{module}.{alias.name}",
                            node_type="import",
                            start_line=node.lineno,
                            end_line=node.lineno,
                        ))

        return nodes

    def _analyze_js(self, code: str) -> list[CodeNode]:
        """Analyze JS/TS code structure using regex."""
        nodes = []
        # Functions
        for m in re.finditer(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="function",
                start_line=line,
                end_line=line + 5,
                signature=f"function {m.group(1)}({m.group(2)})",
            ))
        # Arrow functions
        for m in re.finditer(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="function",
                start_line=line,
                end_line=line + 3,
                signature=f"const {m.group(1)} = ({m.group(2)}) =>",
            ))
        # Classes
        for m in re.finditer(r'(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', code):
            line = code[:m.start()].count('\n') + 1
            sig = f"class {m.group(1)}"
            if m.group(2):
                sig += f" extends {m.group(2)}"
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=sig,
            ))
        return nodes

    def _analyze_go(self, code: str) -> list[CodeNode]:
        """Analyze Go code structure using regex."""
        nodes = []
        for m in re.finditer(r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="function",
                start_line=line,
                end_line=line + 5,
                signature=f"func {m.group(1)}({m.group(2)})",
            ))
        for m in re.finditer(r'type\s+(\w+)\s+struct', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"type {m.group(1)} struct",
            ))
        for m in re.finditer(r'type\s+(\w+)\s+interface', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"type {m.group(1)} interface",
            ))
        return nodes

    def _analyze_rust(self, code: str) -> list[CodeNode]:
        """Analyze Rust code structure using regex."""
        nodes = []
        for m in re.finditer(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="function",
                start_line=line,
                end_line=line + 5,
                signature=f"fn {m.group(1)}({m.group(2)})",
            ))
        for m in re.finditer(r'(?:pub\s+)?struct\s+(\w+)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"struct {m.group(1)}",
            ))
        for m in re.finditer(r'(?:pub\s+)?enum\s+(\w+)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"enum {m.group(1)}",
            ))
        for m in re.finditer(r'(?:pub\s+)?trait\s+(\w+)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"trait {m.group(1)}",
            ))
        return nodes

    def _analyze_java(self, code: str) -> list[CodeNode]:
        """Analyze Java code structure using regex."""
        nodes = []
        # Methods (including constructors)
        for m in re.finditer(
            r'(?:public|protected|private|static|final|abstract|synchronized|native|\s)+'
            r'(?:<[^>]+>\s+)?'
            r'(\w+(?:<[^>]*>)?)\s+(\w+)\s*\(([^)]*)\)',
            code
        ):
            return_type = m.group(1)
            method_name = m.group(2)
            # Skip if it's a class/interface keyword
            if method_name in ('class', 'interface', 'enum', 'record'):
                continue
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=method_name,
                node_type="function",
                start_line=line,
                end_line=line + 5,
                signature=f"{return_type} {method_name}({m.group(3)})",
            ))
        # Classes
        for m in re.finditer(r'(?:public|private|protected)?\s*(?:abstract|final)?\s*class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?', code):
            line = code[:m.start()].count('\n') + 1
            sig = f"class {m.group(1)}"
            if m.group(2):
                sig += f" extends {m.group(2)}"
            if m.group(3):
                sig += f" implements {m.group(3).strip()}"
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=sig,
            ))
        # Interfaces
        for m in re.finditer(r'(?:public|private|protected)?\s*interface\s+(\w+)', code):
            line = code[:m.start()].count('\n') + 1
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=line + 10,
                signature=f"interface {m.group(1)}",
            ))
        return nodes

    def _analyze_c(self, code: str) -> list[CodeNode]:
        """Analyze C/C++ code structure using regex."""
        nodes = []
        # Functions (C-style)
        for m in re.finditer(r'(\w[\w\s\*]+)\s+(\w+)\s*\(([^)]*)\)\s*\{', code):
            return_type = m.group(1).strip()
            func_name = m.group(2)
            line = code[:m.start()].count('\n') + 1
            # Find matching closing brace
            end_line = self._find_closing_brace(code, m.end())
            nodes.append(CodeNode(
                name=func_name,
                node_type="function",
                start_line=line,
                end_line=end_line,
                signature=f"{return_type} {func_name}({m.group(3)})",
            ))
        # Structs
        for m in re.finditer(r'(?:typedef\s+)?struct\s+(\w+)\s*\{', code):
            line = code[:m.start()].count('\n') + 1
            end_line = self._find_closing_brace(code, m.end())
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=end_line,
                signature=f"struct {m.group(1)}",
            ))
        # Classes (C++)
        for m in re.finditer(r'class\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+(\w+))?\s*\{', code):
            line = code[:m.start()].count('\n') + 1
            end_line = self._find_closing_brace(code, m.end())
            sig = f"class {m.group(1)}"
            if m.group(2):
                sig += f" : public {m.group(2)}"
            nodes.append(CodeNode(
                name=m.group(1),
                node_type="class",
                start_line=line,
                end_line=end_line,
                signature=sig,
            ))
        return nodes

    def _find_closing_brace(self, code: str, start: int) -> int:
        """Find the line number of the closing brace."""
        depth = 0
        line = code[:start].count('\n') + 1
        for i, ch in enumerate(code[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return code[:i + 1].count('\n') + 1
            if ch == '\n':
                line += 1
        return line + 5  # fallback

    def find_node(self, code: str, name: str, language: str = "python") -> CodeNode | None:
        """Find a specific node by name."""
        nodes = self.analyze(code, language)
        for node in nodes:
            if node.name == name:
                return node
        return None

    def replace_function(
        self,
        code: str,
        function_name: str,
        new_body: str,
        language: str = "python",
    ) -> str | None:  # noqa: E501
        """Replace a function's body while preserving signature and decorators."""
        lines = code.split('\n')
        nodes = self.analyze(code, language)

        target = None
        for node in nodes:
            if node.name == function_name and node.node_type == "function":
                target = node
                break

        if not target:
            return None

        if language == "python":
            return self._replace_function_python(lines, target, new_body, nodes)
        else:
            return self._replace_function_regex(lines, target, new_body, language)

    def _replace_function_python(
        self,
        lines: list[str],
        target: CodeNode,
        new_body: str,
        nodes: list[CodeNode],
    ) -> str | None:
        """Replace Python function body using AST-aware approach."""
        def_line_idx = target.start_line - 1
        if def_line_idx >= len(lines):
            return None

        def_line = lines[def_line_idx]
        indent = len(def_line) - len(def_line.lstrip())
        indent_str = ' ' * indent

        new_lines = []
        # Include decorators
        for node in nodes:
            if node.name == target.name and node.node_type == "function":
                for i in range(max(0, def_line_idx - 5), def_line_idx):
                    if lines[i].strip().startswith('@'):
                        new_lines.append(lines[i])
                break

        # Add def line
        new_lines.append(lines[def_line_idx])

        # Add new body with proper indentation
        for line in new_body.split('\n'):
            if line.strip():
                new_lines.append(f"{indent_str}    {line}")
            else:
                new_lines.append("")

        # Skip old body
        old_end = target.end_line
        result_lines = lines[:def_line_idx] + new_lines + lines[old_end:]
        return '\n'.join(result_lines)

    def _replace_function_regex(
        self,
        lines: list[str],
        target: CodeNode,
        new_body: str,
        language: str,
    ) -> str | None:
        """Replace function body using regex for non-Python languages."""
        def_line_idx = target.start_line - 1
        if def_line_idx >= len(lines):
            return None

        def_line = lines[def_line_idx]
        indent = len(def_line) - len(def_line.lstrip())
        indent_str = ' ' * indent

        # Find opening brace
        brace_line_idx = None
        for i in range(def_line_idx, min(def_line_idx + 3, len(lines))):
            if '{' in lines[i]:
                brace_line_idx = i
                break

        if brace_line_idx is None:
            return None

        # Find matching closing brace
        depth = 0
        end_line_idx = brace_line_idx
        for i in range(brace_line_idx, len(lines)):
            for ch in lines[i]:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end_line_idx = i
                        break
            if depth == 0:
                break

        # Build new function
        new_lines = []
        # Include everything up to opening brace
        for i in range(def_line_idx, brace_line_idx + 1):
            new_lines.append(lines[i])

        # Add new body
        for line in new_body.split('\n'):
            if line.strip():
                new_lines.append(f"{indent_str}    {line}")
            else:
                new_lines.append("")

        # Add closing brace (preserve any content after it on same line)
        closing_line = lines[end_line_idx]
        brace_pos = closing_line.rfind('}')
        if brace_pos < len(closing_line) - 1:
            suffix = closing_line[brace_pos + 1:]
            new_lines.append(f"{indent_str}}}{suffix}")
        else:
            new_lines.append(f"{indent_str}}}")

        # Skip old function body
        result_lines = lines[:def_line_idx] + new_lines + lines[end_line_idx + 1:]
        return '\n'.join(result_lines)

    def insert_function(
        self,
        code: str,
        function_name: str,
        args: list[str],
        body: str,
        language: str = "python",
        after: str | None = None,
    ) -> str | None:
        """Insert a new function into the code."""
        lines = code.split('\n')

        # Find insertion point
        insert_idx = len(lines) - 1
        if after:
            nodes = self.analyze(code, language)
            for node in nodes:
                if node.name == after:
                    insert_idx = node.end_line
                    break

        # Build function based on language
        args_str = ', '.join(args)

        if language == "python":
            func_lines = [f"def {function_name}({args_str}):"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
        elif language in ("javascript", "typescript", "js", "ts"):
            func_lines = [f"function {function_name}({args_str}) {{"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "go":
            func_lines = [f"func {function_name}({args_str}) {{"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"\t{line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "rust":
            func_lines = [f"fn {function_name}({args_str}) {{"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "java":
            func_lines = [f"public void {function_name}({args_str}) {{"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language in ("c", "cpp", "c++"):
            func_lines = [f"void {function_name}({args_str}) {{"]
            for line in body.split('\n'):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        else:
            # Generic fallback
            func_lines = [f"function {function_name}({args_str}) {{"]  # type: ignore
            for line in body.split('\n'):
                func_lines.append(f"    {line}")
            func_lines.append("}")

        result_lines = lines[:insert_idx] + func_lines + lines[insert_idx:]
        return '\n'.join(result_lines)

    def rename_symbol(self, code: str, old_name: str, new_name: str) -> str:
        """Rename a symbol throughout the code."""
        pattern = r'\b' + re.escape(old_name) + r'\b'
        return re.sub(pattern, new_name, code)

    def add_import(self, code: str, import_line: str, language: str = "python") -> str:
        """Add an import statement to the code."""
        lines = code.split('\n')

        # Find where imports end
        last_import_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if language == "python":
                if stripped.startswith('import ') or stripped.startswith('from '):
                    last_import_idx = i
            elif language in ("javascript", "typescript", "js", "ts"):
                if stripped.startswith('import ') or stripped.startswith('require('):
                    last_import_idx = i
            elif language == "go":
                if stripped.startswith('import ') or stripped.startswith('"'):
                    last_import_idx = i
            elif language == "java":
                if stripped.startswith('import '):
                    last_import_idx = i
            elif language in ("c", "cpp", "c++"):
                if stripped.startswith('#include '):
                    last_import_idx = i
            elif language == "rust":
                if stripped.startswith('use ') or stripped.startswith('extern crate'):
                    last_import_idx = i

        # Check if import already exists
        if import_line.strip() in [l.strip() for l in lines]:
            return code

        # Insert after last import
        lines.insert(last_import_idx + 1, import_line)
        return '\n'.join(lines)


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
    }
    ext = os.path.splitext(file_path)[1].lower()
    return ext_map.get(ext, "unknown")


# Global instance
_ast_editor: ASTEditor | None = None


def get_ast_editor() -> ASTEditor:
    """Get the global AST editor instance."""
    global _ast_editor
    if _ast_editor is None:
        _ast_editor = ASTEditor()
    return _ast_editor
