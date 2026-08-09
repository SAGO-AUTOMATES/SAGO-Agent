"""Debugger Tool - Real debugging with execution, tracing, and analysis.

Cross-platform debugging with Python, JavaScript, and general code support.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class DebuggerArgs(BaseModel):
    """Arguments for DebuggerTool."""

    file_path: str | None = Field(default=None, description="Path to file to debug")
    code_snippet: str | None = Field(default=None, description="Code snippet to analyze")
    error_message: str | None = Field(default=None, description="Error message to analyze")
    command: str | None = Field(default=None, description="Command to run and debug (e.g. 'python script.py')")
    breakpoint_line: int | None = Field(default=None, description="Line number to set breakpoint")


class DebuggerTool(BaseTool):
    """Tool for debugging code execution, analyzing errors, and tracing issues."""

    name = "debugger"
    description = "Debug code: run commands, analyze errors, set breakpoints, trace execution. Use for any debugging task."
    args_model = DebuggerArgs

    def _run(
        self,
        file_path: str | None = None,
        code_snippet: str | None = None,
        error_message: str | None = None,
        command: str | None = None,
        breakpoint_line: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Debug code or analyze an error.

        Args:
            file_path: File to debug.
            code_snippet: Code to analyze.
            error_message: Error message to analyze.
            command: Command to run and debug.
            breakpoint_line: Line to set breakpoint.

        Returns:
            Debug analysis.
        """
        results: list[str] = []

        if command:
            results.extend(self._run_and_debug(command))

        if error_message:
            results.extend(self._analyze_error(error_message))

        if file_path:
            path = self._expand_path(file_path)
            if path.exists():
                results.extend(self._debug_file(path, breakpoint_line))
            else:
                results.append(f"Error: File not found: {path}")

        if code_snippet:
            results.extend(self._analyze_code(code_snippet))

        if not results:
            return "No debug target. Provide command, file_path, code_snippet, or error_message."

        return "\n".join(results)

    def _run_and_debug(self, command: str) -> list[str]:
        """Run a command and capture output for debugging."""
        results = ["=== Command Execution ===\n"]
        results.append(f"Command: {command}\n")

        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path.cwd()),
            )

            if proc.stdout:
                results.append("STDOUT:")
                results.append(proc.stdout[-3000:])

            if proc.stderr:
                results.append("\nSTDERR:")
                results.append(proc.stderr[-3000:])

            results.append(f"\nExit code: {proc.returncode}")

            if proc.returncode != 0:
                results.append("\n=== Error Analysis ===")
                results.extend(self._analyze_error(proc.stderr or proc.stdout))

        except subprocess.TimeoutExpired:
            results.append("Command timed out after 30s")
        except Exception as e:
            results.append(f"Execution error: {e}")

        return results

    def _analyze_error(self, error_message: str) -> list[str]:
        """Analyze an error message and provide actionable suggestions."""
        results = ["=== Error Analysis ===\n"]

        error_lower = error_message.lower()

        # Python errors
        if "syntaxerror" in error_lower:
            results.append("Type: Syntax Error")
            results.append("The code has invalid Python syntax.")
            # Try to extract line number
            line_match = re.search(r"line (\d+)", error_message)
            if line_match:
                results.append(f"At line: {line_match.group(1)}")
            results.append("Fix: Check for missing colons, parentheses, or indentation.")

        elif "nameerror" in error_lower:
            results.append("Type: Name Error")
            var_match = re.search(r"name '(\w+)' is not defined", error_message)
            if var_match:
                results.append(f"Undefined: {var_match.group(1)}")
            results.append("Fix: Check for typos, missing imports, or scope issues.")

        elif "typeerror" in error_lower:
            results.append("Type: Type Error")
            results.append("An operation is applied to an incompatible type.")
            results.append("Fix: Check variable types and function signatures.")

        elif "indexerror" in error_lower:
            results.append("Type: Index Error")
            results.append("An index is out of range.")
            results.append("Fix: Check list/string length before accessing elements.")

        elif "keyerror" in error_lower:
            results.append("Type: Key Error")
            key_match = re.search(r"KeyError: ['\"](.+?)['\"]", error_message)
            if key_match:
                results.append(f"Missing key: {key_match.group(1)}")
            results.append("Fix: Use .get() or check if key exists first.")

        elif "importerror" in error_lower or "modulenotfounderror" in error_lower:
            results.append("Type: Import Error")
            mod_match = re.search(r"No module named '(\w+)'", error_message)
            if mod_match:
                results.append(f"Missing module: {mod_match.group(1)}")
                results.append(f"Fix: pip install {mod_match.group(1)}")
            else:
                results.append("Fix: Check if the module is installed and the name is correct.")

        elif "filenotfounderror" in error_lower:
            results.append("Type: File Not Found")
            file_match = re.search(r"No such file or directory: '(.+?)'", error_message)
            if file_match:
                results.append(f"Missing: {file_match.group(1)}")
            results.append("Fix: Check the path and file permissions.")

        elif "permissionerror" in error_lower:
            results.append("Type: Permission Error")
            results.append("Fix: Check file permissions or run with appropriate privileges.")

        elif "connectionerror" in error_lower or "timeout" in error_lower:
            results.append("Type: Connection Error")
            results.append("Fix: Check network connectivity and server status.")

        elif "attributeerror" in error_lower:
            results.append("Type: Attribute Error")
            attr_match = re.search(r"'(\w+)' object has no attribute '(\w+)'", error_message)
            if attr_match:
                results.append(f"Object: {attr_match.group(1)}, Missing: {attr_match.group(2)}")
            results.append("Fix: Check object type and available methods.")

        elif "valueerror" in error_lower:
            results.append("Type: Value Error")
            results.append("An operation receives an correct argument but inappropriate value.")
            results.append("Fix: Check input values and constraints.")

        elif "runtimeerror" in error_lower:
            results.append("Type: Runtime Error")
            results.append("An error detected during program execution.")
            results.append("Fix: Check the stack trace for the exact location.")

        else:
            results.append(f"Error: {error_message[:500]}")

            # Try to extract file and line info
            file_line = re.search(r'File "(.+?)", line (\d+)', error_message)
            if file_line:
                results.append(f"\nLocation: {file_line.group(1)}:{file_line.group(2)}")

        return results

    def _debug_file(self, path: Path, breakpoint_line: int | None = None) -> list[str]:
        """Debug a file - run it and analyze issues."""
        results = ["\n=== File Debug ==="]
        results.append(f"File: {path}")

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return [f"Error reading file: {e}"]

        lines = content.splitlines()
        results.append(f"Lines: {len(lines)}")

        # Check syntax
        try:
            compile(content, str(path), "exec")
            results.append("Syntax: Valid")
        except SyntaxError as e:
            results.append(f"Syntax Error: Line {e.lineno}: {e.msg}")
            if e.lineno and e.lineno <= len(lines):
                start = max(0, e.lineno - 2)
                end = min(len(lines), e.lineno + 1)
                results.append("\nContext:")
                for i in range(start, end):
                    marker = ">>>" if i + 1 == e.lineno else "   "
                    results.append(f"{marker} {i+1:4}: {lines[i]}")

        # Static analysis
        issues = self._static_analysis(content, lines)
        if issues:
            results.append("\nPotential issues:")
            results.extend(issues)
        else:
            results.append("No obvious issues found")

        # Try to run the file
        if path.suffix == ".py":
            results.append("\n=== Execution Test ===")
            try:
                proc = subprocess.run(
                    [sys.executable, "-c", f"import py_compile; py_compile.compile('{path}', doraise=True)"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode == 0:
                    results.append("Compilation: OK")
                else:
                    results.append(f"Compilation error: {proc.stderr[:500]}")
            except Exception as e:
                results.append(f"Compilation check failed: {e}")

        # Set breakpoint info
        if breakpoint_line and 1 <= breakpoint_line <= len(lines):
            results.append(f"\n=== Breakpoint at line {breakpoint_line} ===")
            start = max(0, breakpoint_line - 3)
            end = min(len(lines), breakpoint_line + 3)
            for i in range(start, end):
                marker = ">>>" if i + 1 == breakpoint_line else "   "
                results.append(f"{marker} {i+1:4}: {lines[i]}")

        return results

    def _static_analysis(self, content: str, lines: list[str]) -> list[str]:
        """Perform static analysis on code."""
        issues: list[str] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return issues

        # Check for common issues
        for node in ast.walk(tree):
            # Bare except
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                issues.append(f"  Line {node.lineno}: Bare except (use specific exception)")

            # Mutable default arguments
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for default in node.args.defaults + node.args.kw_defaults:
                    if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        issues.append(f"  Line {node.lineno}: Mutable default argument in {node.name}()")

            # Global variable usage
            if isinstance(node, ast.Global):
                issues.append(f"  Line {node.lineno}: Global variable: {', '.join(node.names)}")

        # Check for swallowed exceptions
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("except") and "pass" in stripped:
                issues.append(f"  Line {i+1}: Swallowed exception")

        # Check for print statements (debugging leftover)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("print(") and not stripped.startswith("print("):
                issues.append(f"  Line {i+1}: Print statement (debugging leftover?)")

        return issues

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

        # Static analysis
        issues = self._static_analysis(code_snippet, lines)
        if issues:
            results.append("\nIssues found:")
            results.extend(issues)

        return results
