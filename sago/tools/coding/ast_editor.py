"""AST Editor - Structure-aware code editing.

Provides intelligent code editing by understanding the structure of code,
not just text. Supports Python natively via ast module, and regex-based
structure detection for JS/TS/Go/Rust/Java/C/C++.

Enhanced with:
- Deep type inference and annotation extraction
- Parent-child relationship tracking
- Syntax validation with detailed error reporting
- Cross-file symbol resolution
- Structural diffing between code versions
- Improved multi-language parsing
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sago.utils.safe import log_exception

logger = logging.getLogger(__name__)


@dataclass
class CodeNode:
    """A node in the code structure with rich metadata."""

    name: str
    node_type: str  # "function", "class", "method", "import", "variable", "constant"
    start_line: int
    end_line: int
    parent: str | None = None
    decorators: list[str] = field(default_factory=list)
    signature: str = ""
    docstring: str | None = None
    children: list[str] = field(default_factory=list)
    # Enhanced fields
    return_type: str | None = None
    type_annotations: dict[str, str] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    is_async: bool = False
    is_private: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    base_classes: list[str] = field(default_factory=list)
    imports_from: list[str] = field(default_factory=list)
    complexity_estimate: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.node_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent": self.parent,
            "decorators": self.decorators,
            "signature": self.signature,
            "docstring": self.docstring,
            "children": self.children,
            "return_type": self.return_type,
            "type_annotations": self.type_annotations,
            "defaults": self.defaults,
            "is_async": self.is_async,
            "is_private": self.is_private,
            "is_static": self.is_static,
            "is_classmethod": self.is_classmethod,
            "is_property": self.is_property,
            "base_classes": self.base_classes,
            "imports_from": self.imports_from,
            "complexity_estimate": self.complexity_estimate,
        }


@dataclass
class ValidationResult:
    """Result of code validation."""

    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "errors": self.errors,
            "warnings": self.warnings,
            "line": self.line,
            "column": self.column,
        }


@dataclass
class SymbolInfo:
    """Information about a resolved symbol."""

    name: str
    file_path: str
    line: int
    kind: str  # "class", "function", "method", "variable"
    signature: str = ""
    references: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "line": self.line,
            "kind": self.kind,
            "signature": self.signature,
            "references": [{"file": f, "line": ln} for f, ln in self.references],
        }


@dataclass
class StructuralDiff:
    """Structural differences between two code versions."""

    added_functions: list[str] = field(default_factory=list)
    removed_functions: list[str] = field(default_factory=list)
    modified_functions: list[str] = field(default_factory=list)
    added_classes: list[str] = field(default_factory=list)
    removed_classes: list[str] = field(default_factory=list)
    modified_classes: list[str] = field(default_factory=list)
    added_imports: list[str] = field(default_factory=list)
    removed_imports: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added_functions": self.added_functions,
            "removed_functions": self.removed_functions,
            "modified_functions": self.modified_functions,
            "added_classes": self.added_classes,
            "removed_classes": self.removed_classes,
            "modified_classes": self.modified_classes,
            "added_imports": self.added_imports,
            "removed_imports": self.removed_imports,
        }

    def has_changes(self) -> bool:
        return bool(
            self.added_functions
            or self.removed_functions
            or self.modified_functions
            or self.added_classes
            or self.removed_classes
            or self.modified_classes
            or self.added_imports
            or self.removed_imports
        )

    def summary(self) -> str:
        parts = []
        if self.added_functions:
            parts.append(
                f"Added {len(self.added_functions)} function(s): {', '.join(self.added_functions[:5])}"
            )
        if self.removed_functions:
            parts.append(
                f"Removed {len(self.removed_functions)} function(s): {', '.join(self.removed_functions[:5])}"
            )
        if self.modified_functions:
            parts.append(
                f"Modified {len(self.modified_functions)} function(s): {', '.join(self.modified_functions[:5])}"
            )
        if self.added_classes:
            parts.append(
                f"Added {len(self.added_classes)} class(es): {', '.join(self.added_classes[:5])}"
            )
        if self.removed_classes:
            parts.append(
                f"Removed {len(self.removed_classes)} class(es): {', '.join(self.removed_classes[:5])}"
            )
        if self.modified_classes:
            parts.append(
                f"Modified {len(self.modified_classes)} class(es): {', '.join(self.modified_classes[:5])}"
            )
        if self.added_imports:
            parts.append(f"Added {len(self.added_imports)} import(s)")
        if self.removed_imports:
            parts.append(f"Removed {len(self.removed_imports)} import(s)")
        return "; ".join(parts) if parts else "No structural changes"


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
        """Analyze Python code structure using ast with deep metadata extraction."""
        nodes: list[CodeNode] = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return nodes

        # Track parent relationships
        parent_map: dict[int, str] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                # Extract type annotations
                type_annotations = {}
                for arg in node.args.args:
                    if arg.annotation:
                        try:
                            type_annotations[arg.arg] = ast.unparse(arg.annotation)
                        except Exception as e:
                            log_exception(e, "Failed to extract type annotation")

                # Extract defaults
                defaults = {}
                default_values = node.args.defaults
                args_list = node.args.args
                if default_values:
                    offset = len(args_list) - len(default_values)
                    for idx, default in enumerate(default_values):
                        arg_name = args_list[offset + idx].arg
                        try:
                            defaults[arg_name] = ast.unparse(default)
                        except Exception as e:
                            log_exception(e, "Failed to extract default value")

                # Return type
                return_type = None
                if node.returns:
                    try:
                        return_type = ast.unparse(node.returns)
                    except Exception as e:
                        log_exception(e, "Failed to extract return type")

                # Decorators
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        try:
                            decorators.append(ast.unparse(dec))
                        except Exception:
                            decorators.append(f"decorator@line{dec.lineno}")
                    elif isinstance(dec, ast.Call):
                        try:
                            decorators.append(ast.unparse(dec))
                        except Exception:
                            decorators.append(f"decorator@line{dec.lineno}")

                # Signature
                args = [arg.arg for arg in node.args.args]
                if node.args.vararg:
                    args.append(f"*{node.args.vararg.arg}")
                if node.args.kwonlyargs:
                    for kwarg in node.args.kwonlyargs:
                        args.append(kwarg.arg)
                if node.args.kwarg:
                    args.append(f"**{node.args.kwarg.arg}")
                sig = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {node.name}({', '.join(args)})"
                if return_type:
                    sig += f" -> {return_type}"

                docstring = ast.get_docstring(node)

                # Estimate complexity
                complexity = self._estimate_complexity(node)

                # Determine parent
                parent_name = parent_map.get(node.lineno)

                nodes.append(
                    CodeNode(
                        name=node.name,
                        node_type="method" if parent_name else "function",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        parent=parent_name,
                        decorators=decorators,
                        signature=sig,
                        docstring=docstring,
                        return_type=return_type,
                        type_annotations=type_annotations,
                        defaults=defaults,
                        is_async=isinstance(node, ast.AsyncFunctionDef),
                        is_private=node.name.startswith("_"),
                        is_property="property" in decorators,
                        is_classmethod="classmethod" in decorators,
                        is_static="staticmethod" in decorators,
                        complexity_estimate=complexity,
                    )
                )

            elif isinstance(node, ast.ClassDef):
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute):
                        try:
                            decorators.append(ast.unparse(dec))
                        except Exception:
                            decorators.append(f"decorator@line{dec.lineno}")

                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        try:
                            bases.append(ast.unparse(base))
                        except Exception as e:
                            log_exception(e, "Failed to extract base class")

                docstring = ast.get_docstring(node)

                # Track this class as parent for nested functions
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                        parent_map[child.lineno] = node.name

                nodes.append(
                    CodeNode(
                        name=node.name,
                        node_type="class",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        decorators=decorators,
                        signature=f"class {node.name}({', '.join(bases)})",
                        docstring=docstring,
                        base_classes=bases,
                        is_private=node.name.startswith("_"),
                    )
                )

            elif isinstance(node, ast.Import | ast.ImportFrom):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        nodes.append(
                            CodeNode(
                                name=alias.name,
                                node_type="import",
                                start_line=node.lineno,
                                end_line=node.lineno,
                                imports_from=[alias.name],
                            )
                        )
                else:
                    module = node.module or ""
                    for alias in node.names:
                        nodes.append(
                            CodeNode(
                                name=f"{module}.{alias.name}",
                                node_type="import",
                                start_line=node.lineno,
                                end_line=node.lineno,
                                imports_from=[module],
                            )
                        )

            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        nodes.append(
                            CodeNode(
                                name=target.id,
                                node_type="variable",
                                start_line=node.lineno,
                                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                            )
                        )

            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                ann = ""
                if node.annotation:
                    try:
                        ann = ast.unparse(node.annotation)
                    except Exception as e:
                        log_exception(e, "Failed to extract annotation")
                nodes.append(
                    CodeNode(
                        name=node.target.id,
                        node_type="variable",
                        start_line=node.lineno,
                        end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                        return_type=ann if ann else None,
                    )
                )

        return nodes

    def _estimate_complexity(self, node: ast.AST) -> int:
        """Estimate cyclomatic complexity of a function node."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.ExceptHandler)):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                complexity += 1
        return complexity

    def _analyze_js(self, code: str) -> list[CodeNode]:
        """Analyze JS/TS code structure using regex with improved patterns."""
        nodes: list[CodeNode] = []

        # Functions (including overloaded/exported)
        for m in re.finditer(
            r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
            r"(?:\s*:\s*([^\s{]+))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            return_type = m.group(3) if m.group(3) else None
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="function",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"function {m.group(1)}({m.group(2)})",
                    return_type=return_type,
                    is_private=m.group(1).startswith("_"),
                )
            )

        # Arrow functions (const/let/var)
        for m in re.finditer(
            r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*(?::\s*([^\s=]+))?\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*([^\s{]+))?\s*=>",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            return_type = m.group(4) if m.group(4) else m.group(2) if m.group(2) else None
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="function",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"const {m.group(1)} = ({m.group(3)}) =>",
                    return_type=return_type,
                )
            )

        # Classes (including extends, implements)
        for m in re.finditer(
            r"(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:<[^>]*>)?"
            r"(?:\s+extends\s+([\w<>,\s]+))?"
            r"(?:\s+implements\s+([\w<>,\s]+))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            sig = f"class {m.group(1)}"
            bases = []
            if m.group(2):
                sig += f" extends {m.group(2)}"
                bases = [b.strip() for b in m.group(2).split(",")]
            if m.group(3):
                sig += f" implements {m.group(3)}"
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=sig,
                    base_classes=bases,
                )
            )

        # Interfaces
        for m in re.finditer(
            r"(?:export\s+)?interface\s+(\w+)(?:<[^>]*>)?(?:\s+extends\s+([\w<>,\s]+))?", code
        ):
            line = code[: m.start()].count("\n") + 1
            sig = f"interface {m.group(1)}"
            bases = []
            if m.group(2):
                sig += f" extends {m.group(2)}"
                bases = [b.strip() for b in m.group(2).split(",")]
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=sig,
                    base_classes=bases,
                )
            )

        # Type aliases
        for m in re.finditer(r"(?:export\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=line,
                    signature=f"type {m.group(1)}",
                )
            )

        # Imports
        for m in re.finditer(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="import",
                    start_line=line,
                    end_line=line,
                    imports_from=[m.group(1)],
                )
            )

        return nodes

    def _analyze_go(self, code: str) -> list[CodeNode]:
        """Analyze Go code structure using regex with improved patterns."""
        nodes: list[CodeNode] = []

        # Functions (including methods with receivers)
        for m in re.finditer(
            r"func\s+(?:\((\w+)\s+\*?(\w+)\)\s+)?(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)\s*(?:\(([^)]*)\)|([^\s{]*))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            receiver_name = m.group(1)
            receiver_type = m.group(2)
            func_name = m.group(3)
            return_type = m.group(5) if m.group(5) else m.group(4) if m.group(4) else None
            sig = "func "
            if receiver_type:
                sig += f"({receiver_name} *{receiver_type}) "
            sig += f"{func_name}({m.group(4)})"
            nodes.append(
                CodeNode(
                    name=func_name,
                    node_type="method" if receiver_type else "function",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=sig,
                    parent=receiver_type,
                    return_type=return_type,
                )
            )

        # Structs
        for m in re.finditer(r"type\s+(\w+)\s+struct\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"type {m.group(1)} struct",
                )
            )

        # Interfaces
        for m in re.finditer(r"type\s+(\w+)\s+interface\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"type {m.group(1)} interface",
                )
            )

        # Imports
        for m in re.finditer(r'"([^"]+)"', code):
            # Only match import blocks
            before = code[: m.start()].rstrip()
            if before.endswith("import") or before.endswith("("):
                nodes.append(
                    CodeNode(
                        name=m.group(1),
                        node_type="import",
                        start_line=code[: m.start()].count("\n") + 1,
                        end_line=code[: m.start()].count("\n") + 1,
                        imports_from=[m.group(1)],
                    )
                )

        return nodes

    def _analyze_rust(self, code: str) -> list[CodeNode]:
        """Analyze Rust code structure using regex with improved patterns."""
        nodes: list[CodeNode] = []

        # Functions (including pub, async, const, unsafe)
        for m in re.finditer(
            r"(?:pub\s+)?(?:async\s+)?(?:const\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)"
            r"(?:\s*->\s*([^\s{]+))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="function",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"fn {m.group(1)}({m.group(2)})",
                    return_type=m.group(3),
                    is_private=not code[m.start() : m.start() + 3].startswith("pub"),
                )
            )

        # Structs (including pub, derive)
        for m in re.finditer(
            r"(?:#\[derive\([^\)]*\)\]\s*)?(?:pub\s+)?struct\s+(\w+)(?:<[^>]*>)?(?:\s*\{|\s*\()",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            if "{" in code[m.start() : m.start() + 100]:
                end_line = self._estimate_end_line(code, m.start(), "{", "}")
            else:
                end_line = line  # Tuple struct
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=end_line,
                    signature=f"struct {m.group(1)}",
                    is_private=not code[m.start() : m.start() + 3].startswith("pub"),
                )
            )

        # Enums
        for m in re.finditer(r"(?:pub\s+)?enum\s+(\w+)(?:<[^>]*>)?\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"enum {m.group(1)}",
                    is_private=not code[m.start() : m.start() + 3].startswith("pub"),
                )
            )

        # Traits
        for m in re.finditer(r"(?:pub\s+)?trait\s+(\w+)(?:<[^>]*>)?\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"trait {m.group(1)}",
                )
            )

        # Impl blocks
        for m in re.finditer(r"impl(?:<[^>]*>)?\s+(\w+)(?:<[^>]*>)?\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=f"impl {m.group(1)}",
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"impl {m.group(1)}",
                )
            )

        # Use statements (imports)
        for m in re.finditer(r"(?:pub\s+)?use\s+([^;]+);", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1).strip(),
                    node_type="import",
                    start_line=line,
                    end_line=line,
                    imports_from=[m.group(1).strip()],
                )
            )

        return nodes

    def _analyze_java(self, code: str) -> list[CodeNode]:
        """Analyze Java code structure using regex with improved patterns."""
        nodes: list[CodeNode] = []

        # Methods (including constructors, annotations)
        for m in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s+)*"
            r"(?:public|protected|private|static|final|abstract|synchronized|native|default|\s)+"
            r"(?:<[^>]+>\s+)?"
            r"(\w+(?:<[^>]*>)?)\s+(\w+)\s*\(([^)]*)\)"
            r"(?:\s*throws\s+[\w,\s]+)?",
            code,
        ):
            return_type = m.group(1)
            method_name = m.group(2)
            if method_name in ("class", "interface", "enum", "record", "package"):
                continue
            line = code[: m.start()].count("\n") + 1

            # Extract annotations
            decorators = []
            for dec_match in re.finditer(r"@(\w+)", code[max(0, m.start() - 200) : m.start()]):
                decorators.append(dec_match.group(1))

            nodes.append(
                CodeNode(
                    name=method_name,
                    node_type="function",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"{return_type} {method_name}({m.group(3)})",
                    return_type=return_type,
                    decorators=decorators,
                )
            )

        # Classes (including generics, extends, implements)
        for m in re.finditer(
            r"(?:@\w+(?:\([^)]*\))?\s+)*"
            r"(?:public|private|protected)?\s*(?:abstract|final|static)?\s*class\s+(\w+)"
            r"(?:<[^>]*>)?"
            r"(?:\s+extends\s+([\w<>,.]+))?"
            r"(?:\s+implements\s+([\w<>,.\s]+))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            sig = f"class {m.group(1)}"
            bases = []
            if m.group(2):
                sig += f" extends {m.group(2)}"
                bases.extend([b.strip() for b in m.group(2).split(",")])
            if m.group(3):
                sig += f" implements {m.group(3)}"
                bases.extend([b.strip() for b in m.group(3).split(",")])
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=sig,
                    base_classes=bases,
                )
            )

        # Interfaces
        for m in re.finditer(
            r"(?:public|private|protected)?\s*interface\s+(\w+)(?:<[^>]*>)?"
            r"(?:\s+extends\s+([\w<>,.\s]+))?",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            sig = f"interface {m.group(1)}"
            bases = []
            if m.group(2):
                sig += f" extends {m.group(2)}"
                bases = [b.strip() for b in m.group(2).split(",")]
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=sig,
                    base_classes=bases,
                )
            )

        # Enums
        for m in re.finditer(r"(?:public|private|protected)?\s*enum\s+(\w+)", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"enum {m.group(1)}",
                )
            )

        # Imports
        for m in re.finditer(r"import\s+([\w.]+)\s*;", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="import",
                    start_line=line,
                    end_line=line,
                    imports_from=[m.group(1)],
                )
            )

        return nodes

    def _analyze_c(self, code: str) -> list[CodeNode]:
        """Analyze C/C++ code structure using regex with improved patterns."""
        nodes: list[CodeNode] = []

        # Functions (C-style, including templates)
        for m in re.finditer(
            r"(?:template\s*<[^>]*>\s*)?"
            r"([\w\s\*<>]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const\s*)?(?:override\s*)?(?:=\s*(?:0|default|delete)\s*)?\{",
            code,
        ):
            return_type = m.group(1).strip()
            func_name = m.group(2)
            line = code[: m.start()].count("\n") + 1
            end_line = self._estimate_end_line(code, m.start(), "{", "}")
            nodes.append(
                CodeNode(
                    name=func_name,
                    node_type="function",
                    start_line=line,
                    end_line=end_line,
                    signature=f"{return_type} {func_name}({m.group(3)})",
                    is_private=func_name.startswith("_"),
                )
            )

        # Structs
        for m in re.finditer(r"(?:typedef\s+)?struct\s+(\w*)\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            end_line = self._estimate_end_line(code, m.start(), "{", "}")
            name = m.group(1) or f"struct_{line}"
            nodes.append(
                CodeNode(
                    name=name,
                    node_type="class",
                    start_line=line,
                    end_line=end_line,
                    signature=f"struct {name}",
                )
            )

        # Classes (C++)
        for m in re.finditer(
            r"(?:template\s*<[^>]*>\s*)?"
            r"class\s+(\w+)"
            r"(?:\s*:\s*(?:public|private|protected)\s+([\w<>,\s]+))?\s*\{",
            code,
        ):
            line = code[: m.start()].count("\n") + 1
            end_line = self._estimate_end_line(code, m.start(), "{", "}")
            sig = f"class {m.group(1)}"
            bases = []
            if m.group(2):
                sig += f" : {m.group(2).strip()}"
                bases = [b.strip().split()[-1] for b in m.group(2).split(",") if b.strip()]
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=end_line,
                    signature=sig,
                    base_classes=bases,
                )
            )

        # Namespaces
        for m in re.finditer(r"namespace\s+(\w+)\s*\{", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="class",
                    start_line=line,
                    end_line=self._estimate_end_line(code, m.start(), "{", "}"),
                    signature=f"namespace {m.group(1)}",
                )
            )

        # Includes
        for m in re.finditer(r"#include\s+[<\"]([^>\"]+)[>\"]", code):
            line = code[: m.start()].count("\n") + 1
            nodes.append(
                CodeNode(
                    name=m.group(1),
                    node_type="import",
                    start_line=line,
                    end_line=line,
                    imports_from=[m.group(1)],
                )
            )

        return nodes

    def _estimate_end_line(self, code: str, start: int, open_char: str, close_char: str) -> int:
        """Estimate end line by counting brace depth, aware of strings and comments.

        Skips braces inside string literals (single, double, triple-quoted)
        and line/block comments to avoid false matches.
        """
        depth = 0
        found_open = False
        line = code[:start].count("\n") + 1
        i = start
        length = len(code)

        while i < length:
            ch = code[i]

            # Skip single-line comments
            if ch == "/" and i + 1 < length and code[i + 1] == "/":
                # Skip to end of line
                while i < length and code[i] != "\n":
                    i += 1
                continue

            # Skip single-line comments (Python/Ruby style)
            if ch == "#":
                while i < length and code[i] != "\n":
                    i += 1
                continue

            # Skip block comments /* ... */
            if ch == "/" and i + 1 < length and code[i + 1] == "*":
                i += 2
                while i + 1 < length:
                    if code[i] == "*" and code[i + 1] == "/":
                        i += 2
                        break
                    i += 1
                continue

            # Skip multi-line strings (triple-quoted)
            if ch in ('"', "'"):
                quote = ch
                # Check for triple quote
                if i + 2 < length and code[i + 1] == quote and code[i + 2] == quote:
                    triple = quote * 3
                    i += 3
                    while i + 2 < length:
                        if code[i : i + 3] == triple:
                            i += 3
                            break
                        i += 1
                    continue
                # Single/double quoted string
                i += 1
                while i < length:
                    if code[i] == "\\":
                        i += 2  # Skip escaped character
                        continue
                    if code[i] == quote:
                        i += 1
                        break
                    i += 1
                continue

            # Skip single-quoted strings (char literals in C/Go)
            if ch == "'" and i + 2 < length and code[i + 2] == "'":
                i += 3
                continue

            # Count braces
            if ch == open_char:
                depth += 1
                found_open = True
            elif ch == close_char:
                depth -= 1
                if found_open and depth == 0:
                    return code[: i + 1].count("\n") + 1

            if ch == "\n":
                line += 1

            i += 1

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
        lines = code.split("\n")
        nodes = self.analyze(code, language)

        target = None
        for node in nodes:
            if node.name == function_name and node.node_type in ("function", "method"):
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
        indent_str = " " * indent

        new_lines = []
        # Include decorators
        for node in nodes:
            if node.name == target.name and node.node_type in ("function", "method"):
                for i in range(max(0, def_line_idx - 5), def_line_idx):
                    if lines[i].strip().startswith("@"):
                        new_lines.append(lines[i])
                break

        # Add def line
        new_lines.append(lines[def_line_idx])

        # Add new body with proper indentation
        for line in new_body.split("\n"):
            if line.strip():
                new_lines.append(f"{indent_str}    {line}")
            else:
                new_lines.append("")

        # Skip old body
        old_end = target.end_line
        result_lines = lines[:def_line_idx] + new_lines + lines[old_end:]
        return "\n".join(result_lines)

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
        indent_str = " " * indent

        # Find opening brace
        brace_line_idx = None
        for i in range(def_line_idx, min(def_line_idx + 3, len(lines))):
            if "{" in lines[i]:
                brace_line_idx = i
                break

        if brace_line_idx is None:
            return None

        # Find matching closing brace
        depth = 0
        end_line_idx = brace_line_idx
        for i in range(brace_line_idx, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end_line_idx = i
                        break
            if depth == 0:
                break

        # Build new function
        new_lines = []
        for i in range(def_line_idx, brace_line_idx + 1):
            new_lines.append(lines[i])

        for line in new_body.split("\n"):
            if line.strip():
                new_lines.append(f"{indent_str}    {line}")
            else:
                new_lines.append("")

        closing_line = lines[end_line_idx]
        brace_pos = closing_line.rfind("}")
        if brace_pos < len(closing_line) - 1:
            suffix = closing_line[brace_pos + 1 :]
            new_lines.append(f"{indent_str}}}{suffix}")
        else:
            new_lines.append(f"{indent_str}}}")

        result_lines = lines[:def_line_idx] + new_lines + lines[end_line_idx + 1 :]
        return "\n".join(result_lines)

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
        lines = code.split("\n")

        insert_idx = len(lines) - 1
        if after:
            nodes = self.analyze(code, language)
            for node in nodes:
                if node.name == after:
                    insert_idx = node.end_line
                    break

        args_str = ", ".join(args)

        if language == "python":
            func_lines = [f"def {function_name}({args_str}):"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
        elif language in ("javascript", "typescript", "js", "ts"):
            func_lines = [f"function {function_name}({args_str}) {{"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "go":
            func_lines = [f"func {function_name}({args_str}) {{"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"\t{line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "rust":
            func_lines = [f"fn {function_name}({args_str}) {{"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language == "java":
            func_lines = [f"public void {function_name}({args_str}) {{"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        elif language in ("c", "cpp", "c++"):
            func_lines = [f"void {function_name}({args_str}) {{"]
            for line in body.split("\n"):
                if line.strip():
                    func_lines.append(f"    {line}")
                else:
                    func_lines.append("")
            func_lines.append("}")
        else:
            func_lines = [f"function {function_name}({args_str}) {{"]  # type: ignore
            for line in body.split("\n"):
                func_lines.append(f"    {line}")
            func_lines.append("}")

        result_lines = lines[:insert_idx] + func_lines + lines[insert_idx:]
        return "\n".join(result_lines)

    def rename_symbol(self, code: str, old_name: str, new_name: str) -> str:
        """Rename a symbol throughout the code."""
        pattern = r"\b" + re.escape(old_name) + r"\b"
        return re.sub(pattern, new_name, code)

    def add_import(self, code: str, import_line: str, language: str = "python") -> str:
        """Add an import statement to the code."""
        lines = code.split("\n")

        last_import_idx = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if language == "python":
                if stripped.startswith("import ") or stripped.startswith("from "):
                    last_import_idx = i
            elif language in ("javascript", "typescript", "js", "ts"):
                if stripped.startswith("import ") or stripped.startswith("require("):
                    last_import_idx = i
            elif language == "go":
                if stripped.startswith("import ") or stripped.startswith('"'):
                    last_import_idx = i
            elif language == "java":
                if stripped.startswith("import "):
                    last_import_idx = i
            elif language in ("c", "cpp", "c++"):
                if stripped.startswith("#include "):
                    last_import_idx = i
            elif language == "rust":
                if stripped.startswith("use ") or stripped.startswith("extern crate"):
                    last_import_idx = i

        if import_line.strip() in [line.strip() for line in lines]:
            return code

        lines.insert(last_import_idx + 1, import_line)
        return "\n".join(lines)

    # ---- Enhanced methods ----

    def validate_syntax(self, code: str, language: str = "python") -> ValidationResult:
        """Validate code syntax and return detailed results."""
        if language == "python":
            return self._validate_python_syntax(code)
        elif language in ("javascript", "typescript", "js", "ts"):
            return self._validate_js_syntax(code)
        elif language == "go":
            return self._validate_go_syntax(code)
        elif language == "rust":
            return self._validate_rust_syntax(code)
        elif language == "java":
            return self._validate_java_syntax(code)
        elif language in ("c", "cpp", "c++"):
            return self._validate_c_syntax(code)
        return ValidationResult(
            success=True, warnings=["Validation not supported for this language"]
        )

    def _validate_python_syntax(self, code: str) -> ValidationResult:
        """Validate Python syntax with detailed error reporting."""
        try:
            ast.parse(code)
            return ValidationResult(success=True)
        except SyntaxError as e:
            return ValidationResult(
                success=False,
                errors=[f"SyntaxError: {e.msg}"],
                line=e.lineno,
                column=e.offset,
            )
        except Exception as e:
            return ValidationResult(success=False, errors=[f"Parse error: {e}"])

    def _validate_js_syntax(self, code: str) -> ValidationResult:
        """Validate JS/TS syntax using basic checks."""
        errors = []
        warnings = []

        # Check balanced braces
        brace_depth = 0
        for i, ch in enumerate(code):
            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth -= 1
            if brace_depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing brace at line {line}")
                break
        if brace_depth > 0:
            errors.append(f"Unmatched opening brace ({brace_depth} unclosed)")

        # Check balanced parentheses
        paren_depth = 0
        for i, ch in enumerate(code):
            if ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
            if paren_depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing paren at line {line}")
                break
        if paren_depth > 0:
            errors.append(f"Unmatched opening paren ({paren_depth} unclosed)")

        # Check for common syntax issues
        if re.search(r"=\s*{", code) and not re.search(r"=>|function|class", code):
            warnings.append("Object literal may need function/class keyword")

        return ValidationResult(success=len(errors) == 0, errors=errors, warnings=warnings)

    def _validate_go_syntax(self, code: str) -> ValidationResult:
        """Validate Go syntax using basic checks."""
        errors = []
        # Check balanced braces
        depth = 0
        for i, ch in enumerate(code):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing brace at line {line}")
                break
        if depth > 0:
            errors.append(f"Unmatched opening brace ({depth} unclosed)")
        return ValidationResult(success=len(errors) == 0, errors=errors)

    def _validate_rust_syntax(self, code: str) -> ValidationResult:
        """Validate Rust syntax using basic checks."""
        errors = []
        depth = 0
        for i, ch in enumerate(code):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing brace at line {line}")
                break
        if depth > 0:
            errors.append(f"Unmatched opening brace ({depth} unclosed)")
        return ValidationResult(success=len(errors) == 0, errors=errors)

    def _validate_java_syntax(self, code: str) -> ValidationResult:
        """Validate Java syntax using basic checks."""
        errors = []
        depth = 0
        for i, ch in enumerate(code):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing brace at line {line}")
                break
        if depth > 0:
            errors.append(f"Unmatched opening brace ({depth} unclosed)")
        return ValidationResult(success=len(errors) == 0, errors=errors)

    def _validate_c_syntax(self, code: str) -> ValidationResult:
        """Validate C/C++ syntax using basic checks."""
        errors = []
        depth = 0
        for i, ch in enumerate(code):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            if depth < 0:
                line = code[:i].count("\n") + 1
                errors.append(f"Unmatched closing brace at line {line}")
                break
        if depth > 0:
            errors.append(f"Unmatched opening brace ({depth} unclosed)")
        return ValidationResult(success=len(errors) == 0, errors=errors)

    def validate_edit(
        self, original_code: str, edited_code: str, language: str = "python"
    ) -> ValidationResult:
        """Validate that an edit didn't introduce syntax errors."""
        result = self.validate_syntax(edited_code, language)
        if not result.success:
            result.errors.insert(0, "Edit introduced syntax errors:")
        return result

    def diff_structures(
        self, old_code: str, new_code: str, language: str = "python"
    ) -> StructuralDiff:
        """Compute structural differences between two code versions."""
        old_nodes = self.analyze(old_code, language)
        new_nodes = self.analyze(new_code, language)

        diff = StructuralDiff()

        # Build lookup maps
        old_funcs = {n.name: n for n in old_nodes if n.node_type in ("function", "method")}
        new_funcs = {n.name: n for n in new_nodes if n.node_type in ("function", "method")}
        old_classes = {n.name: n for n in old_nodes if n.node_type == "class"}
        new_classes = {n.name: n for n in new_nodes if n.node_type == "class"}
        old_imports = {n.name: n for n in old_nodes if n.node_type == "import"}
        new_imports = {n.name: n for n in new_nodes if n.node_type == "import"}

        # Functions
        for name in new_funcs:
            if name not in old_funcs:
                diff.added_functions.append(name)
            elif new_funcs[name].signature != old_funcs[name].signature:
                diff.modified_functions.append(name)
        for name in old_funcs:
            if name not in new_funcs:
                diff.removed_functions.append(name)

        # Classes
        for name in new_classes:
            if name not in old_classes:
                diff.added_classes.append(name)
            elif new_classes[name].signature != old_classes[name].signature:
                diff.modified_classes.append(name)
        for name in old_classes:
            if name not in new_classes:
                diff.removed_classes.append(name)

        # Imports
        for name in new_imports:
            if name not in old_imports:
                diff.added_imports.append(name)
        for name in old_imports:
            if name not in new_imports:
                diff.removed_imports.append(name)

        return diff

    def resolve_symbol(self, name: str, root_dir: str | Path = ".") -> SymbolInfo | None:
        """Resolve a symbol by searching all source files in the directory."""
        root = Path(root_dir)
        if not root.exists():
            return None

        ignored = {
            ".git",
            ".venv",
            "__pycache__",
            "node_modules",
            "dist",
            "build",
            ".tox",
            ".mypy_cache",
        }

        # Search Python files first
        for py_file in root.rglob("*.py"):
            if any(part in ignored for part in py_file.parts):
                continue
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                nodes = self.analyze(code, "python")
                for node in nodes:
                    if node.name == name and node.node_type in ("class", "function", "method"):
                        rel_path = str(py_file.relative_to(root))
                        return SymbolInfo(
                            name=name,
                            file_path=rel_path,
                            line=node.start_line,
                            kind=node.node_type,
                            signature=node.signature,
                        )
            except Exception:
                continue

        # Search JS/TS files
        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx"):
            for js_file in root.rglob(ext):
                if any(part in ignored for part in js_file.parts):
                    continue
                try:
                    code = js_file.read_text(encoding="utf-8", errors="ignore")
                    nodes = self.analyze(code, "javascript")
                    for node in nodes:
                        if node.name == name and node.node_type in ("class", "function"):
                            rel_path = str(js_file.relative_to(root))
                            return SymbolInfo(
                                name=name,
                                file_path=rel_path,
                                line=node.start_line,
                                kind=node.node_type,
                                signature=node.signature,
                            )
                except Exception:
                    continue

        # Search Go files
        for go_file in root.rglob("*.go"):
            if any(part in ignored for part in go_file.parts):
                continue
            try:
                code = go_file.read_text(encoding="utf-8", errors="ignore")
                nodes = self.analyze(code, "go")
                for node in nodes:
                    if node.name == name and node.node_type in ("class", "function", "method"):
                        rel_path = str(go_file.relative_to(root))
                        return SymbolInfo(
                            name=name,
                            file_path=rel_path,
                            line=node.start_line,
                            kind=node.node_type,
                            signature=node.signature,
                        )
            except Exception:
                continue

        # Search Rust files
        for rs_file in root.rglob("*.rs"):
            if any(part in ignored for part in rs_file.parts):
                continue
            try:
                code = rs_file.read_text(encoding="utf-8", errors="ignore")
                nodes = self.analyze(code, "rust")
                for node in nodes:
                    if node.name == name and node.node_type in ("class", "function"):
                        rel_path = str(rs_file.relative_to(root))
                        return SymbolInfo(
                            name=name,
                            file_path=rel_path,
                            line=node.start_line,
                            kind=node.node_type,
                            signature=node.signature,
                        )
            except Exception:
                continue

        # Search Java files
        for java_file in root.rglob("*.java"):
            if any(part in ignored for part in java_file.parts):
                continue
            try:
                code = java_file.read_text(encoding="utf-8", errors="ignore")
                nodes = self.analyze(code, "java")
                for node in nodes:
                    if node.name == name and node.node_type in ("class", "function"):
                        rel_path = str(java_file.relative_to(root))
                        return SymbolInfo(
                            name=name,
                            file_path=rel_path,
                            line=node.start_line,
                            kind=node.node_type,
                            signature=node.signature,
                        )
            except Exception:
                continue

        return None


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
