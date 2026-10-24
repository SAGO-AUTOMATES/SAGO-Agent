"""Session tools for Sago."""

from typing import Any

from sago.tools.session.session_manager import SessionManagerArgs, SessionManagerTool


def load_session(session_id: str) -> dict[str, Any]:
    """Load session helper for session tools."""
    tool = SessionManagerTool()
    tool._load_session(session_id)
    return tool._sessions.get(session_id, {})


__all__ = ["SessionManagerTool", "SessionManagerArgs", "load_session"]
