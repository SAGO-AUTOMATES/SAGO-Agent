"""AST Edit Tool - Structure-aware code editing.

Edit code by structure (function name, class name) instead of text matching.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool


class ASTEditArgs(BaseModel):
    """Arguments for ASTEditTool."""

    action: str = Field(
        description="Action: analyze, replace_function, insert_function, rename, add_import"
    )
    file_path: str = Field(description="Path to the file to edit")
    target: str = Field(default="", description="Target name (function/class to edit)")
    new_code: str = Field(default="", description="New code for replacement/insertion")
    language: str = Field(default="auto", description="Language: auto, python, javascript, typescript, go, rust")
    extra: str = Field(default="", description="Extra params (comma-separated args for insert, new name for rename)")


class ASTEditTool(BaseTool):
    """Tool for structure-aware code editing using AST analysis."""

    name = "ast_edit"
    description = (
        "Edit code by structure, not text. Can analyze code structure, "
        "replace function bodies, insert functions, rename symbols, add imports."
    )
    args_model = ASTEditArgs

    def _run(
        self,
        action: str,
        file_path: str,
        target: str = "",
        new_code: str = "",
        language: str = "auto",
        extra: str = "",
        **kwargs: Any,
    ) -> str:
        """Run AST edit action."""
        from sago.tools.coding.ast_editor import get_ast_editor, detect_language

        editor = get_ast_editor()

        # Auto-detect language
        if language == "auto":
            language = detect_language(file_path)

        # Read file
        try:
            from pathlib import Path
            path = Path(file_path)
            if not path.exists():
                return f"File not found: {file_path}"
            code = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

        if action == "analyze":
            nodes = editor.analyze(code, language)
            if not nodes:
                return f"No structure found in {file_path} (language: {language})"
            lines = [f"=== {language.upper()} Structure: {file_path} ==="]
            for node in nodes:
                prefix = "  " if node.node_type == "method" else ""
                lines.append(f"{prefix}[{node.node_type}] {node.signature} (lines {node.start_line}-{node.end_line})")
            return "\n".join(lines)

        elif action == "replace_function":
            if not target:
                return "Error: target (function name) required"
            result = editor.replace_function(code, target, new_code, language)
            if result is None:
                return f"Could not find or replace function '{target}'"
            path.write_text(result, encoding="utf-8")
            return f"Replaced function '{target}' in {file_path}"

        elif action == "insert_function":
            if not target:
                return "Error: target (function name) required"
            args = [a.strip() for a in extra.split(",") if a.strip()] if extra else []
            result = editor.insert_function(code, target, args, new_code, language)
            if result is None:
                return f"Could not insert function '{target}'"
            path.write_text(result, encoding="utf-8")
            return f"Inserted function '{target}' in {file_path}"

        elif action == "rename":
            if not target or not extra:
                return "Error: target (old name) and extra (new name) required"
            result = editor.rename_symbol(code, target, extra)
            path.write_text(result, encoding="utf-8")
            return f"Renamed '{target}' to '{extra}' in {file_path}"

        elif action == "add_import":
            if not new_code:
                return "Error: new_code (import statement) required"
            result = editor.add_import(code, new_code, language)
            path.write_text(result, encoding="utf-8")
            return f"Added import to {file_path}"

        else:
            return f"Unknown action: {action}. Use: analyze, replace_function, insert_function, rename, add_import"
