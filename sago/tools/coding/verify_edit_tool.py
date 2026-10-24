"""Verify Edit Tool - Check if an edit would apply and pass syntax guard without writing."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool
from sago.tools.file.resilient_editor import ResilientEditor

logger = logging.getLogger("sago.tools.coding.verify_edit_tool")


class VerifyEditArgs(BaseModel):
    file_path: str = Field(description="Path to file")
    old_string: str = Field(description="String to find")
    new_string: str = Field(description="Replacement string")


class VerifyEditTool(BaseTool):
    name = "verify_edit"
    description = (
        "PREFER before editing: check if an edit would apply and pass syntax guard (no write)."
    )
    args_model = VerifyEditArgs

    def _run(self, file_path: str, old_string: str, new_string: str, **kwargs: Any) -> str:
        path = self._expand_path(file_path)
        if not path.exists():
            return f"Error: File not found: {path}"
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading file: {e}"

        match = ResilientEditor.find_best_match(content, old_string)
        if not match.found:
            return f"Would NOT apply: target not found (tier={match.match_tier})."

        new_content = content[: match.start_idx] + new_string + content[match.end_idx :]
        ok, msg = ResilientEditor.syntax_guard(content, new_content, str(path))
        if not ok:
            return f"Would apply but FAILS syntax guard: {msg}"
        return f"Would apply cleanly (tier={match.match_tier}, confidence={match.confidence:.2f})."
