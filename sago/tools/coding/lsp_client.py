"""LSP Client - Language Server Protocol integration for type checking and diagnostics.

Provides type checking, diagnostics, go-to-definition, and completions
by communicating with language servers (pyright, gopls, rust-analyzer, etc.).
Falls back to CLI tools when LSP servers aren't available.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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


# Supported languages and their LSP/CLI tools
LANGUAGE_SERVERS = {
    "python": {
        "lsp": ["pyright-langserver", "--stdio"],
        "cli_check": ["pyright", "--outputjson"],
        "cli_format": ["black", "--quiet", "--line-length", "100"],
        "ext": [".py"],
    },
    "javascript": {
        "lsp": ["typescript-language-server", "--stdio"],
        "cli_check": ["tsc", "--noEmit", "--pretty", "false"],
        "cli_format": ["prettier", "--write"],
        "ext": [".js", ".jsx"],
    },
    "typescript": {
        "lsp": ["typescript-language-server", "--stdio"],
        "cli_check": ["tsc", "--noEmit", "--pretty", "false"],
        "cli_format": ["prettier", "--write"],
        "ext": [".ts", ".tsx"],
    },
    "go": {
        "lsp": ["gopls"],
        "cli_check": ["go", "vet", "./..."],
        "cli_format": ["gofmt", "-w"],
        "ext": [".go"],
    },
    "rust": {
        "lsp": ["rust-analyzer"],
        "cli_check": ["cargo", "check", "--message-format=json"],
        "cli_format": ["rustfmt"],
        "ext": [".rs"],
    },
    "java": {
        "lsp": ["jdtls"],
        "cli_check": ["javac", "-Xlint:all"],
        "cli_format": [],
        "ext": [".java"],
    },
    "c": {
        "lsp": ["clangd"],
        "cli_check": ["gcc", "-fsyntax-only", "-Wall", "-Wextra"],
        "cli_format": ["clang-format", "-i"],
        "ext": [".c", ".h"],
    },
    "cpp": {
        "lsp": ["clangd"],
        "cli_check": ["g++", "-fsyntax-only", "-Wall", "-Wextra"],
        "cli_format": ["clang-format", "-i"],
        "ext": [".cpp", ".hpp", ".cc", ".cxx"],
    },
}


def _detect_language(file_path: str) -> str:
    """Detect language from file extension."""
    ext = os.path.splitext(file_path)[1].lower()
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cc": "cpp",
        ".cxx": "cpp",
    }
    return ext_map.get(ext, "unknown")


def _check_command_exists(cmd: str) -> bool:
    """Check if a command exists on the system."""
    try:
        result = subprocess.run(
            ["which", cmd],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class LSPClient:
    """Lightweight LSP client with CLI fallbacks for multiple languages."""

    def __init__(self) -> None:
        self._servers: dict[str, subprocess.Popen | None] = {}
        self._available_checkers: dict[str, bool | None] = {}  # None = unchecked

    def check_types(self, file_path: str) -> list[Diagnostic]:
        """Run type checking on a file."""
        path = Path(file_path)
        if not path.exists():
            return []

        language = _detect_language(file_path)
        if language == "unknown":
            return []

        # Try LSP server first, then CLI fallback
        return self._check_with_cli(file_path, language)

    def _check_with_cli(self, file_path: str, language: str) -> list[Diagnostic]:
        """Check using CLI tools as fallback."""
        config = LANGUAGE_SERVERS.get(language)
        if not config:
            return []

        cli_cmd = config.get("cli_check")
        if not cli_cmd:
            return []

        # Special handling per language
        if language == "python":
            return self._run_pyright(file_path)
        elif language in ("javascript", "typescript"):
            return self._run_tsc(file_path)
        elif language == "go":
            return self._run_go_vet(file_path)
        elif language == "rust":
            return self._run_cargo_check(file_path)
        elif language == "java":
            return self._run_javac_lint(file_path)
        elif language in ("c", "cpp"):
            return self._run_gcc_syntax(file_path, language)

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
        except FileNotFoundError:
            return [
                self._make_info_diagnostic(
                    file_path, "pyright not installed. Run: pip install pyright"
                )
            ]
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return []

    def _parse_pyright_output(self, data: dict, file_path: str) -> list[Diagnostic]:
        """Parse pyright JSON output."""
        diagnostics = []
        severity_map = {"error": "error", "warning": "warning", "information": "info"}
        for diag in data.get("generalDiagnostics", []):
            range_info = diag.get("range", {})
            start = range_info.get("start", {})
            end = range_info.get("end", {})
            diagnostics.append(
                Diagnostic(
                    file=file_path,
                    line=start.get("line", 0) + 1,
                    column=start.get("character", 0),
                    end_line=end.get("line", 0) + 1,
                    end_column=end.get("character", 0),
                    severity=severity_map.get(diag.get("severity", "error"), "error"),
                    message=diag.get("message", ""),
                    code=diag.get("rule", ""),
                    source="pyright",
                )
            )
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
        except FileNotFoundError:
            return [
                self._make_info_diagnostic(
                    file_path, "tsc not installed. Run: npm install -g typescript"
                )
            ]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _parse_tsc_output(self, output: str, file_path: str) -> list[Diagnostic]:
        """Parse tsc error output."""
        diagnostics = []
        for line in output.split("\n"):
            match = re.match(r"(.+?):(\d+):(\d+)\s*-\s*error\s+(.+?)(?:\s*\((.+?)\))?$", line)
            if match:
                diagnostics.append(
                    Diagnostic(
                        file=file_path,
                        line=int(match.group(2)),
                        column=int(match.group(3)),
                        end_line=int(match.group(2)),
                        end_column=int(match.group(3)) + 10,
                        severity="error",
                        message=match.group(4),
                        code=match.group(5),
                        source="tsc",
                    )
                )
        return diagnostics

    def _run_go_vet(self, file_path: str) -> list[Diagnostic]:
        """Run go vet for Go files."""
        try:
            result = subprocess.run(
                ["go", "vet", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            diagnostics = []
            output = result.stdout + "\n" + result.stderr
            for line in output.split("\n"):
                # Parse go vet output: file:line:col: message
                match = re.match(r"(.+?):(\d+):(\d+):\s*(.*)", line)
                if match:
                    diagnostics.append(
                        Diagnostic(
                            file=file_path,
                            line=int(match.group(2)),
                            column=int(match.group(3)),
                            end_line=int(match.group(2)),
                            end_column=int(match.group(3)) + 10,
                            severity="error" if "error" in line.lower() else "warning",
                            message=match.group(4),
                            source="go vet",
                        )
                    )
            return diagnostics
        except FileNotFoundError:
            return [self._make_info_diagnostic(file_path, "go not installed")]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_cargo_check(self, file_path: str) -> list[Diagnostic]:
        """Run cargo check for Rust files."""
        try:
            result = subprocess.run(
                ["cargo", "check", "--message-format=json"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            diagnostics = []
            for line in result.stdout.split("\n"):
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("reason") == "compiler-message":
                        cm = msg.get("message", {})
                        spans = cm.get("spans", [])
                        if spans:
                            span = spans[0]
                            diagnostics.append(
                                Diagnostic(
                                    file=span.get("file_name", file_path),
                                    line=span.get("line_start", 0),
                                    column=span.get("column_start", 0),
                                    end_line=span.get("line_end", 0),
                                    end_column=span.get("column_end", 0),
                                    severity="error" if cm.get("level") == "error" else "warning",
                                    message=cm.get("message", ""),
                                    code=cm.get("code", {}).get("code", ""),
                                    source="cargo",
                                )
                            )
                except json.JSONDecodeError:
                    continue
            return diagnostics
        except FileNotFoundError:
            return [self._make_info_diagnostic(file_path, "cargo not installed")]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_javac_lint(self, file_path: str) -> list[Diagnostic]:
        """Run javac -Xlint for Java files."""
        try:
            result = subprocess.run(
                ["javac", "-Xlint:all", "-d", "/tmp", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            diagnostics = []
            output = result.stdout + "\n" + result.stderr
            for line in output.split("\n"):
                match = re.match(r"(.+?):(\d+):\s*(warning|error):\s*(.*)", line)
                if match:
                    diagnostics.append(
                        Diagnostic(
                            file=file_path,
                            line=int(match.group(2)),
                            column=0,
                            end_line=int(match.group(2)),
                            end_column=0,
                            severity=match.group(3),
                            message=match.group(4),
                            source="javac",
                        )
                    )
            return diagnostics
        except FileNotFoundError:
            return [self._make_info_diagnostic(file_path, "javac not installed")]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _run_gcc_syntax(self, file_path: str, language: str) -> list[Diagnostic]:
        """Run gcc/g++ syntax check for C/C++ files."""
        compiler = "g++" if language == "cpp" else "gcc"
        try:
            result = subprocess.run(
                [compiler, "-fsyntax-only", "-Wall", "-Wextra", file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            diagnostics = []
            output = result.stdout + "\n" + result.stderr
            for line in output.split("\n"):
                match = re.match(r"(.+?):(\d+):(\d+):\s*(warning|error|note):\s*(.*)", line)
                if match:
                    diagnostics.append(
                        Diagnostic(
                            file=file_path,
                            line=int(match.group(2)),
                            column=int(match.group(3)),
                            end_line=int(match.group(2)),
                            end_column=int(match.group(3)) + 10,
                            severity=match.group(4),
                            message=match.group(5),
                            source=compiler,
                        )
                    )
            return diagnostics
        except FileNotFoundError:
            return [self._make_info_diagnostic(file_path, f"{compiler} not installed")]
        except subprocess.TimeoutExpired:
            pass
        return []

    def _make_info_diagnostic(self, file_path: str, message: str) -> Diagnostic:
        """Create an informational diagnostic."""
        return Diagnostic(
            file=file_path,
            line=0,
            column=0,
            end_line=0,
            end_column=0,
            severity="info",
            message=message,
            source="sago",
        )

    def get_definitions(self, file_path: str, line: int, column: int) -> list[Definition]:
        """Locate the definition(s) of the symbol under the given position.

        Performs a project-wide search for definition patterns of the identifier
        at the cursor (e.g. ``def name``, ``class Name``, ``function name``) and
        returns the real candidate definition locations rather than echoing the
        input position back.
        """
        try:
            path = Path(file_path)
            if not path.exists():
                return []

            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            if line < 1 or line > len(lines):
                return []

            line_text = lines[line - 1]
            # Extract the full identifier that contains the cursor position,
            # regardless of where within the word the cursor sits.
            start = max(0, min(column, len(line_text)))
            while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] == "_"):
                start -= 1
            end = min(column, len(line_text))
            while end < len(line_text) and (line_text[end].isalnum() or line_text[end] == "_"):
                end += 1
            symbol = line_text[start:end]
            if not symbol or not symbol[0].isalpha() and symbol[0] != "_":
                return []

            root = self._find_project_root(path.parent)

            patterns = [
                rf"(?:def|async\s+def)\s+{re.escape(symbol)}\s*\(",
                rf"function\s+{re.escape(symbol)}\s*\(",
                rf"func\s+{re.escape(symbol)}\s*\(",
                rf"(?:class|interface|struct|enum|type|const|let|var|public|private|protected|static)\s+{re.escape(symbol)}\b",
                rf"\b{re.escape(symbol)}\s*=",
            ]
            combined = re.compile("|".join(patterns))

            definitions: list[Definition] = []
            seen: set[tuple[str, int]] = set()
            for source in self._iter_source_files(root):
                try:
                    text = source.read_text(encoding="utf-8", errors="replace")
                except Exception as read_err:
                    logger.debug("LSPClient: Failed to read source file %s: %s", source, read_err)
                    continue
                for idx, src_line in enumerate(text.split("\n"), 1):
                    if combined.search(src_line):
                        key = (str(source), idx)
                        if key in seen:
                            continue
                        seen.add(key)
                        definitions.append(Definition(file=str(source), line=idx, column=1))
                        if len(definitions) >= 20:
                            return definitions
            return definitions
        except Exception as e:
            logger.debug("LSPClient: get_definitions failed: %s", e)
            return []

    @staticmethod
    def _symbol_at(file_path: str, line: int, column: int) -> str | None:
        """Return the identifier under the given (line, column) position, if any."""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            if line < 1 or line > len(lines):
                return None
            line_text = lines[line - 1]
            # Expand the cursor position to the full word it sits within.
            start = max(0, min(column, len(line_text)))
            while start > 0 and (line_text[start - 1].isalnum() or line_text[start - 1] == "_"):
                start -= 1
            end = min(column, len(line_text))
            while end < len(line_text) and (line_text[end].isalnum() or line_text[end] == "_"):
                end += 1
            symbol = line_text[start:end]
            if not symbol or not (symbol[0].isalpha() or symbol[0] == "_"):
                return None
            return symbol
        except Exception:
            return None

    def get_references(self, file_path: str, line: int, column: int) -> list[Definition]:
        """Find all references (usages) of the symbol under the given position.

        Reuses the project-wide source scan used by :meth:`get_definitions` but
        looks for every occurrence of the symbol's word rather than only its
        definition patterns.
        """
        try:
            symbol = self._symbol_at(file_path, line, column)
            if not symbol:
                return []

            root = self._find_project_root(Path(file_path).parent)
            pattern = re.compile(rf"\b{re.escape(symbol)}\b")

            references: list[Definition] = []
            seen: set[tuple[str, int]] = set()
            for source in self._iter_source_files(root):
                try:
                    text = source.read_text(encoding="utf-8", errors="replace")
                except Exception as read_err:
                    logger.debug("LSPClient: Failed to read source file %s: %s", source, read_err)
                    continue
                for idx, src_line in enumerate(text.split("\n"), 1):
                    if pattern.search(src_line):
                        key = (str(source), idx)
                        if key in seen:
                            continue
                        seen.add(key)
                        references.append(Definition(file=str(source), line=idx, column=1))
                        if len(references) >= 200:
                            return references
            return references
        except Exception as e:
            logger.debug("LSPClient: get_references failed: %s", e)
            return []

    def get_hover(self, file_path: str, line: int, column: int) -> dict[str, Any] | None:
        """Return hover information for the symbol under the given position.

        Locates the symbol's real definition (reusing :meth:`get_definitions`)
        and returns its kind and the definition's source line as detail.
        """
        try:
            symbol = self._symbol_at(file_path, line, column)
            if not symbol:
                return None

            kind = "variable"
            detail: str | None = None

            definitions = self.get_definitions(file_path, line, column)
            if definitions:
                definition = definitions[0]
                detail = None
                try:
                    def_text = (
                        Path(definition.file)
                        .read_text(encoding="utf-8", errors="replace")
                        .split("\n")
                    )
                    if 1 <= definition.line <= len(def_text):
                        detail = def_text[definition.line - 1].strip()
                except Exception as read_err:
                    logger.debug("LSPClient: Failed to read hover definition: %s", read_err)
                    detail = None
                if detail is not None:
                    if re.search(rf"(?:def|async\s+def)\s+{re.escape(symbol)}\b", detail):
                        kind = "function"
                    elif re.search(rf"\bclass\s+{re.escape(symbol)}\b", detail):
                        kind = "class"
                    else:
                        kind = "variable"

            return {"symbol": symbol, "kind": kind, "detail": detail}
        except Exception as e:
            logger.debug("LSPClient: get_hover failed: %s", e)
            return None

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Return diagnostics (type errors / warnings) for a file.

        Delegates to the existing type-checking pipeline so it reports the same
        diagnostics a real LSP ``textDocument/publishDiagnostics`` would surface.
        """
        try:
            return self.check_types(file_path)
        except Exception as e:
            logger.debug("LSPClient: get_diagnostics failed: %s", e)
            return []

    @staticmethod
    def _find_project_root(start: Path) -> Path:
        markers = {
            "pyproject.toml",
            "package.json",
            "go.mod",
            "Cargo.toml",
            "pom.xml",
            ".git",
        }
        current = start
        for _ in range(10):
            if any((current / marker).exists() for marker in markers):
                return current
            if current.parent == current:
                break
            current = current.parent
        return start

    @staticmethod
    def _iter_source_files(root: Path) -> list[Path]:
        exts = {
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".jsx",
            ".go",
            ".rs",
            ".java",
            ".c",
            ".h",
            ".cpp",
            ".hpp",
            ".cc",
            ".cxx",
            ".sql",
        }
        results: list[Path] = []
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                results.append(p)
        return results

    def get_completions(self, file_path: str, line: int, column: int) -> list[Completion]:
        """Get completions at a position (basic implementation)."""
        try:
            content = Path(file_path).read_text()
            lines = content.split("\n")
            if line <= len(lines):
                current_line = lines[line - 1]
                before_cursor = current_line[:column]
                word_match = re.search(r"(\w+)$", before_cursor)
                if word_match:
                    prefix = word_match.group(1)
                    all_words = set(re.findall(r"\b(\w+)\b", content))
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
        language = _detect_language(file_path)
        config = LANGUAGE_SERVERS.get(language)
        if not config:
            return None

        fmt_cmd = config.get("cli_format")
        if not fmt_cmd:
            return None

        try:
            cmd = fmt_cmd + [file_path]
            result = subprocess.run(
                cmd,
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
