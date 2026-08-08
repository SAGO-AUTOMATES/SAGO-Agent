"""Debugger Tool - Debug code execution and trace issues.

Cross-platform debugging with Python and general code support.
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DebuggerArgs(BaseModel):
    """Arguments for DebuggerTool."""

    file_path: str | None = Field(default=None, description="Path to Python file to debug")
    code_snippet: str | None = Field(default=None, description="Python code snippet to analyze")
    error_message: str | None = Field(default=None, description="Error message to analyze")


class DebuggerTool(BaseTool):
    """Tool for debugging code execution and analyzing errors."""

    name = "debugger"
    description = "Debug code execution, analyze errors, and trace issues."
    args_model = DebuggerArgs

    def _run(
        self,
        file_path: str | None = None,
        code_snippet: str | None = None,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Debug code or analyze an error.

        Args:
            file_path: Python file to debug.
            code_snippet: Code to analyze.
            error_message: Error message to analyze.

        Returns:
            Debug analysis.
        """
        results: list[str] = []

        if error_message:
            results.extend(self._analyze_error(error_message))

        if file_path:
            path = self._expand_path(file_path)
            if path.exists():
                results.extend(self._debug_file(path))
            else:
                results.append(f"Error: File not found: {path}")

        if code_snippet:
            results.extend(self._analyze_code(code_snippet))

        if not results:
            return "No debug target specified. Provide file_path, code_snippet, or error_message."

        return "\n".join(results)

    def _analyze_error(self, error_message: str) -> list[str]:
        """Analyze an error message and provide suggestions."""
        results = ["=== Error Analysis ===\n"]

        # Parse common Python errors
        error_lower = error_message.lower()

        if "syntaxerror" in error_lower:
            results.append("Type: Syntax Error")
            results.append("The code has invalid Python syntax.")
            results.append("Check for missing colons, parentheses, or indentation.")

        elif "nameerror" in error_lower:
            results.append("Type: Name Error")
            results.append("A variable or function is not defined.")
            results.append("Check for typos and missing imports.")

        elif "typeerror" in error_lower:
            results.append("Type: Type Error")
            results.append("An operation is applied to an incompatible type.")
            results.append("Check variable types and function signatures.")

        elif "indexerror" in error_lower:
            results.append("Type: Index Error")
            results.append("An index is out of range.")
            results.append("Check list/string length before accessing elements.")

        elif "keyerror" in error_lower:
            results.append("Type: Key Error")
            results.append("A dictionary key does not exist.")
            results.append("Use .get() or check if key exists first.")

        elif "importerror" in error_lower or "modulenotfounderror" in error_lower:
            results.append("Type: Import Error")
            results.append("A module could not be imported.")
            results.append("Check if the module is installed and the name is correct.")

        elif "filenotfounderror" in error_lower:
            results.append("Type: File Not Found")
            results.append("A file or directory does not exist.")
            results.append("Check the path and file permissions.")

        elif "permissionerror" in error_lower:
            results.append("Type: Permission Error")
            results.append("Insufficient permissions to access the resource.")
            results.append("Check file permissions or run with appropriate privileges.")

        elif "connectionerror" in error_lower or "timeout" in error_lower:
            results.append("Type: Connection Error")
            results.append("A network connection failed or timed out.")
            results.append("Check network connectivity and server status.")

        else:
            results.append(f"Error message: {error_message}")

        return results

    def _debug_file(self, path: Path) -> list[str]:
        """Debug a Python file for common issues."""
        results = ["\n=== File Debug ==="]

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [f"Error reading file: {e}"]

        lines = content.splitlines()
        results.append(f"File: {path}")
        results.append(f"Lines: {len(lines)}")

        # Check for syntax errors
        try:
            compile(content, str(path), "exec")
            results.append("Syntax: Valid")
        except SyntaxError as e:
            results.append(f"Syntax Error: Line {e.lineno}: {e.msg}")

        # Check for common issues
        issues: list[str] = []

        # Unused imports (simplified)
        imports = set()
        used_names = set()
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import "):
                names = stripped.replace("import ", "").split(",")
                for name in names:
                    imports.add(name.strip().split(" as ")[0])
            elif stripped.startswith("from "):
                parts = stripped.split(" import ")
                if len(parts) > 1:
                    names = parts[1].split(",")
                    for name in names:
                        imports.add(name.strip().split(" as ")[0])

        # Check for bare except
        for i, line in enumerate(lines):
            if "except:" in line.strip():
                issues.append(f"  Line {i + 1}: Bare except (use specific exception)")
            if "except Exception:" in line.strip() and "pass" in lines[i + 1].strip() if i + 1 < len(lines) else False:
                issues.append(f"  Line {i + 1}: Swallowed exception")

        if issues:
            results.append("\nPotential issues:")
            results.extend(issues)
        else:
            results.append("No obvious issues found")

        return results

    def _analyze_code(self, code_snippet: str) -> list[str]:
        """Analyze a code snippet for issues."""
        results = ["\n=== Code Analysis ==="]

        # Try to compile
        try:
            compile(code_snippet, "<snippet>", "exec")
            results.append("Syntax: Valid")
        except SyntaxError as e:
            results.append(f"Syntax Error: Line {e.lineno}: {e.msg}")

        # Analyze structure
        lines = code_snippet.splitlines()
        results.append(f"Lines: {len(lines)}")
        results.append(f"Characters: {len(code_snippet)}")

        return results
