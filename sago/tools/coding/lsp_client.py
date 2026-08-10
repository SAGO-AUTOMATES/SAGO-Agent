"""LSP Client - Language Server Protocol integration for type checking and diagnostics.

Provides type checking, diagnostics, go-to-definition, and completions
by communicating with language servers (pyright, typescript-language-server, etc.).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Diagnostic:
    """A language diagnostic."""
    file: str
    line: int
    column: int
    end_line: int
    end_column: int
    severity: str  # "error", "warning", "info", "hint"
    message: str
    code: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "column": self.column,
            "severity": self.severity,
            "message": self.message,
            "code": self.code,
        }

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column} [{self.severity}] {self.message}"


@dataclass
class Completion:
    """A code completion item."""
    label: str
    kind: str
    detail: str | None = None
    documentation: str | None = None
    insert_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "kind": self.kind,
            "detail": self.detail,
        }


@dataclass
class Definition:
    """A definition location."""
    file: str
    line: int
    column: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "column": self.column}


class LSPClient:
    """Lightweight LSP client using pyright/typescript-language-server."""

    def __init__(self) -> None:
        self._servers: dict[str, subprocess.Popen | None] = {}

    def _get_server_command(self, language: str) -> list[str] | None:
        """Get the LSP server command for a language."""
        servers = {
            "python": ["pyright-langserver", "--stdio"],
            "javascript": ["typescript-language-server", "--stdio"],
            "typescript": ["typescript-language-server", "--stdio"],
        }
        return servers.get(language)

    def check_types(self, file_path: str) -> list[Diagnostic]:
        """Run type checking on a file using pyright."""
        path = Path(file_path)
        if not path.exists():
            return []

        # Use pyright for Python files
        if path.suffix == ".py":
            return self._run_pyright(file_path)
        elif path.suffix in (".js", ".ts", ".jsx", ".tsx"):
            return self._run_tsc(file_path)
        return []

    def _run_pyright(self, file_path: str) -> list[Diagnostic]:
        """Run pyright type checker."""
        try:
            result = subprocess.run(
                ["pyright", "--outputjson", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 or result.stdout:
                data = json.loads(result.stdout)
                return self._parse_pyright_output(data, file_path)
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        return []

    def _parse_pyright_output(self, data: dict, file_path: str) -> list[Diagnostic]:
        """Parse pyright JSON output."""
        diagnostics = []
        for diag in data.get("generalDiagnostics", []):
            severity_map = {
                "error": "error",
                "warning": "warning",
                "information": "info",
            }
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            end = range_info.get("end", {})
            diagnostics.append(Diagnostic(
                file=file_path,
                line=start.get("line", 0) + 1,
                column=start.get("character", 0),
                end_line=end.get("line", 0) + 1,
                end_column=end.get("character", 0),
                severity=severity_map.get(diag.get("severity", "error"), "error"),
                message=diag.get("message", ""),
                code=diag.get("rule", ""),
                source="pyright",
            ))
        return diagnostics

    def _run_tsc(self, file_path: str) -> list[Diagnostic]:
        """Run TypeScript compiler for type checking."""
        try:
            result = subprocess.run(
                ["tsc", "--noEmit", "--pretty", "false", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return self._parse_tsc_output(result.stderr, file_path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return []

    def _parse_tsc_output(self, output: str, file_path: str) -> list[Diagnostic]:
        """Parse tsc error output."""
        diagnostics = []
        for line in output.split('\n'):
            match = __import__('re').match(
                r'(.+?):(\d+):(\d+)\s*-\s*error\s+(.+?)(?:\s*\((.+?)\))?$',
                line
            )
            if match:
                diagnostics.append(Diagnostic(
                    file=file_path,
                    line=int(match.group(2)),
                    column=int(match.group(3)),
                    end_line=int(match.group(2)),
                    end_column=int(match.group(3)) + 10,
                    severity="error",
                    message=match.group(4),
                    code=match.group(5),
                    source="tsc",
                ))
        return diagnostics

    def get_definitions(self, file_path: str, line: int, column: int) -> list[Definition]:
        """Get definitions at a position (basic implementation)."""
        # For now, return basic info
        return [Definition(file=file_path, line=line, column=column)]

    def get_completions(self, file_path: str, line: int, column: int) -> list[Completion]:
        """Get completions at a position (basic implementation)."""
        # Basic completions based on file content
        try:
            content = Path(file_path).read_text()
            lines = content.split('\n')
            if line <= len(lines):
                current_line = lines[line - 1]
                # Get word being typed
                before_cursor = current_line[:column]
                import re
                word_match = re.search(r'(\w+)$', before_cursor)
                if word_match:
                    prefix = word_match.group(1)
                    # Find all words in file
                    all_words = set(re.findall(r'\b(\w+)\b', content))
                    return [
                        Completion(label=w, kind="text")
                        for w in sorted(all_words)
                        if w.startswith(prefix) and w != prefix
                    ][:20]
        except Exception:
            pass
        return []

    def format_code(self, file_path: str) -> str | None:
        """Format code using language-specific formatter."""
        path = Path(file_path)
        if path.suffix == ".py":
            try:
                result = subprocess.run(
                    ["black", "--quiet", "--line-length", "100", file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return Path(file_path).read_text()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        elif path.suffix in (".js", ".ts", ".jsx", ".tsx"):
            try:
                result = subprocess.run(
                    ["prettier", "--write", file_path],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    return Path(file_path).read_text()
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return None


# Global instance
_lsp_client: LSPClient | None = None


def get_lsp_client() -> LSPClient:
    """Get the global LSP client."""
    global _lsp_client
    if _lsp_client is None:
        _lsp_client = LSPClient()
    return _lsp_client
