"""Session Manager Tool - Manage persistent sessions.

Stores and retrieves session data across tool calls.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from sago.tools.base import BaseTool

logger = logging.getLogger("sago.tools.session.session_manager")


class SessionManagerArgs(BaseModel):
    """Arguments for SessionManagerTool."""

    operation: Literal["get", "set", "delete", "list", "clear"] = Field(
        description="Operation to perform"
    )
    key: str | None = Field(default=None, description="Session key")
    value: str | None = Field(default=None, description="Value to store (for set)")
    session_id: str = Field(default="default", description="Session ID")


class SessionManagerTool(BaseTool):
    """Tool for managing persistent sessions across tool calls."""

    name = "session_manager"
    description = "Store and retrieve data across tool calls using a persistent session."
    args_model = SessionManagerArgs

    def __init__(self) -> None:
        super().__init__()
        self._sessions: dict[str, dict[str, Any]] = {}
        from sago.paths import get_sago_home

        self._session_dir = get_sago_home() / "sessions"
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def _run(
        self,
        operation: str,
        key: str | None = None,
        value: str | None = None,
        session_id: str = "default",
        **kwargs: Any,
    ) -> str:
        """Perform a session operation.

        Args:
            operation: Operation type.
            key: Session key.
            value: Value to store.
            session_id: Session identifier.

        Returns:
            Operation result.
        """
        # Load session from disk
        self._load_session(session_id)

        if operation == "get":
            if key is None:
                return "Error: key required for get operation"
            if key not in self._sessions.get(session_id, {}):
                return f"Key '{key}' not found in session '{session_id}'"
            return str(self._sessions[session_id][key])

        elif operation == "set":
            if key is None or value is None:
                return "Error: key and value required for set operation"
            if session_id not in self._sessions:
                self._sessions[session_id] = {}
            self._sessions[session_id][key] = value
            self._save_session(session_id)
            return f"Set '{key}' in session '{session_id}'"

        elif operation == "delete":
            if key is None:
                return "Error: key required for delete operation"
            if key in self._sessions.get(session_id, {}):
                del self._sessions[session_id][key]
                self._save_session(session_id)
                return f"Deleted '{key}' from session '{session_id}'"
            return f"Key '{key}' not found in session '{session_id}'"

        elif operation == "list":
            session_data = self._sessions.get(session_id, {})
            if not session_data:
                return f"Session '{session_id}' is empty"
            lines = [f"Session '{session_id}' keys:"]
            for k, v in session_data.items():
                preview = str(v)[:50] + "..." if len(str(v)) > 50 else str(v)
                lines.append(f"  {k}: {preview}")
            return "\n".join(lines)

        elif operation == "clear":
            self._sessions[session_id] = {}
            self._save_session(session_id)
            return f"Cleared session '{session_id}'"

        return f"Error: Unknown operation: {operation}"

    def _load_session(self, session_id: str) -> None:
        """Load session data from disk."""
        session_file = self._session_dir / f"{session_id}.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                self._sessions[session_id] = data
            except (json.JSONDecodeError, OSError):
                self._sessions[session_id] = {}

    def _save_session(self, session_id: str) -> None:
        """Save session data to disk."""
        session_file = self._session_dir / f"{session_id}.json"
        data = self._sessions.get(session_id, {})
        session_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
