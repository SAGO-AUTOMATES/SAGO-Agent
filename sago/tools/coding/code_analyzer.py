"""Code Analyzer Tool - Analyze code for structure and issues.

Cross-platform code analysis using AST and regex patterns.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class CodeAnalyzerArgs(BaseModel):
    """Arguments for CodeAnalyzerTool."""

    file_path: str = Field(description="Path to the code file to analyze")
    analysis_type: str = Field(
        default="all",
        description="Type of analysis: 'structure', 'complexity', 'issues', 'all'"
    )


class CodeAnalyzerTool(BaseTool):
    """Tool for analyzing code structure, complexity, and potential issues."""

    name = "code_analyzer"
    description = "Analyze code for structure, complexity, and potential issues."
    args_model = CodeAnalyzerArgs

    def _run(
        self,
        file_path: str,
        analysis_type: str = "all",
        **kwargs: Any,
    ) -> str:
        """Analyze a code file.

        Args:
            file_path: Path to the code file.
            analysis_type: Type of analysis.

        Returns:
            Analysis report.
        """
        path = self._expand_path(file_path)

        if not path.exists():
            return f"Error: File not found: {path}"
        if not path.is_file():
            return f"Error: Not a file: {path}"

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"Error reading file: {e}"

        ext = path.suffix.lower()
        lines = content.splitlines()
        results: list[str] = []

        # Basic stats
        results.append(f"=== Code Analysis: {path.name} ===\n")
        results.append(f"Lines of code: {len(lines)}")
        results.append(f"File size: {len(content)} bytes")
        results.append(f"Language: {ext or 'unknown'}")

        if analysis_type in ("structure", "all"):
            results.append("\n--- Structure ---")
            results.extend(self._analyze_structure(content, ext))

        if analysis_type in ("complexity", "all"):
            results.append("\n--- Complexity ---")
            results.extend(self._analyze_complexity(content, ext))

        if analysis_type in ("issues", "all"):
            results.append("\n--- Potential Issues ---")
            results.extend(self._analyze_issues(content, ext, lines))

        return "\n".join(results)

    def _analyze_structure(self, content: str, ext: str) -> list[str]:
        """Analyze code structure."""
        results: list[str] = []

        if ext == ".py":
            try:
                tree = ast.parse(content)
                classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
                functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]

                results.append(f"Classes: {len(classes)}")
                for cls in classes:
                    methods = [n for n in ast.iter_child_nodes(cls) if isinstance(n, ast.FunctionDef)]
                    results.append(f"  {cls.name} ({len(methods)} methods, line {cls.lineno})")

                results.append(f"\nFunctions: {len(functions)}")
                for func in functions:
                    args = len(func.args.args)
                    results.append(f"  {func.name}({args} args, line {func.lineno})")
            except SyntaxError:
                results.append("  (Python syntax error - cannot parse AST)")
        else:
            # Generic pattern matching for other languages
            class_pattern = re.compile(r"(?:class|interface|struct|enum)\s+(\w+)")
            func_pattern = re.compile(r"(?:def|function|fn|func)\s+(\w+)")

            classes = class_pattern.findall(content)
            functions = func_pattern.findall(content)

            results.append(f"Classes/Structs: {len(classes)}")
            for c in classes:
                results.append(f"  {c}")
            results.append(f"\nFunctions: {len(functions)}")
            for f in functions:
                results.append(f"  {f}")

        return results

    def _analyze_complexity(self, content: str, ext: str) -> list[str]:
        """Analyze code complexity."""
        results: list[str] = []

        # Count cyclomatic complexity indicators
        complexity_keywords = [
            "if ", "elif ", "else:", "for ", "while ", "except ",
            "catch", "switch", "case ", "&&", "||", "?",
        ]
        count = sum(content.count(kw) for kw in complexity_keywords)
        results.append(f"Cyclomatic complexity indicators: {count}")

        # Nesting depth
        max_indent = 0
        for line in content.splitlines():
            stripped = line.lstrip()
            if stripped:
                indent = len(line) - len(stripped)
                max_indent = max(max_indent, indent)
        results.append(f"Maximum nesting depth: {max_indent // 4}")

        # Long lines
        long_lines = [i + 1 for i, line in enumerate(content.splitlines()) if len(line) > 120]
        if long_lines:
            results.append(f"Lines > 120 chars: {len(long_lines)} (lines: {long_lines[:10]})")
        else:
            results.append("No lines exceed 120 characters")

        return results

    def _analyze_issues(self, content: str, ext: str, lines: list[str]) -> list[str]:
        """Analyze potential code issues."""
        results: list[str] = []

        # TODO/FIXME/HACK comments
        todo_pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|NOTE)", re.IGNORECASE)
        todos = [(i + 1, line.strip()) for i, line in enumerate(lines) if todo_pattern.search(line)]
        if todos:
            results.append(f"TODO/FIXME markers ({len(todos)}):")
            for num, line in todos[:10]:
                results.append(f"  Line {num}: {line}")

        # Empty except blocks
        if ext == ".py":
            empty_except = re.compile(r"except.*:\s*\n\s*pass")
            matches = empty_except.findall(content)
            if matches:
                results.append(f"Empty except blocks: {len(matches)}")

        # Debug prints
        if ext == ".py":
            debug_prints = re.compile(r"^\s*print\(", re.MULTILINE)
            matches = debug_prints.findall(content)
            if matches:
                results.append(f"Debug print statements: {len(matches)}")

        # Console.log in JS/TS
        if ext in (".js", ".ts", ".jsx", ".tsx"):
            console_logs = len(re.findall(r"console\.(log|debug|warn|error)", content))
            if console_logs:
                results.append(f"Console statements: {console_logs}")

        # Magic numbers
        magic_numbers = re.compile(r"(?<![.\w])\d{3,}(?!\w)")
        numbers = magic_numbers.findall(content)
        if numbers:
            results.append(f"Magic numbers found: {len(numbers)}")

        return results
