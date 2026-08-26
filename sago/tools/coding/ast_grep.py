"""AST-based structural code searching tool across multiple languages."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.coding.ast_grep")


class AstGrepArgs(BaseModel):
    """Arguments for AstGrepTool."""

    pattern_type: str = Field(
        description="Type of symbol to search: 'function', 'class', 'decorator', 'call', or 'import'"
    )
    name_pattern: str = Field(description="Name or substring pattern to match")
    directory: str = Field(default=".", description="Root search directory")
    max_matches: int = Field(default=30, description="Max matches to return")


class AstGrepTool(BaseTool):
    """Search codebases structurally using AST parsing rather than raw text matching."""

    name = "ast_grep"
    description = "Search code structurally using Abstract Syntax Tree patterns for classes, functions, and decorators."
    args_model = AstGrepArgs
    risk_level = "safe"

    def _run(
        self,
        pattern_type: str,
        name_pattern: str,
        directory: str = ".",
        max_matches: int = 30,
        **kwargs: Any,
    ) -> str:
        root = Path(directory)
        if not root.exists():
            return f"Error: Directory '{directory}' not found."

        matches = []
        p_type = pattern_type.lower().strip()
        pattern = name_pattern.lower().strip()
        ignored = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}

        for py_file in root.rglob("*.py"):
            if len(matches) >= max_matches:
                break
            if any(part in ignored for part in py_file.parts):
                continue

            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
                rel_path = py_file.relative_to(root)

                for node in ast.walk(tree):
                    if len(matches) >= max_matches:
                        break

                    # Function definition
                    if p_type in ("function", "def") and isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef)
                    ):
                        if pattern in node.name.lower():
                            args = [a.arg for a in node.args.args]
                            matches.append(
                                f"• {rel_path}:{node.lineno} def {node.name}({', '.join(args)})"
                            )

                    # Class definition
                    elif p_type in ("class", "type") and isinstance(node, ast.ClassDef):
                        if pattern in node.name.lower():
                            bases = [getattr(b, "id", "") for b in node.bases if hasattr(b, "id")]
                            base_str = f"({', '.join(bases)})" if bases else ""
                            matches.append(
                                f"• {rel_path}:{node.lineno} class {node.name}{base_str}"
                            )

                    # Decorator
                    elif p_type == "decorator" and isinstance(
                        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                    ):
                        for dec in node.decorator_list:
                            dec_name = getattr(dec, "id", "") or getattr(
                                getattr(dec, "func", None), "id", ""
                            )
                            if pattern in dec_name.lower():
                                matches.append(
                                    f"• {rel_path}:{node.lineno} @{dec_name} on {node.name}"
                                )

                    # Imports
                    elif p_type == "import" and isinstance(node, (ast.Import, ast.ImportFrom)):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if pattern in alias.name.lower():
                                    matches.append(
                                        f"• {rel_path}:{node.lineno} import {alias.name}"
                                    )
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            if pattern in node.module.lower():
                                matches.append(
                                    f"• {rel_path}:{node.lineno} from {node.module} import ..."
                                )
            except Exception:
                continue

        if not matches:
            return f"No AST matches found for pattern '{name_pattern}' of type '{pattern_type}'."

        return (
            f"Found {len(matches)} AST match(es) for '{name_pattern}' [{pattern_type}]:\n"
            + "\n".join(matches)
        )
