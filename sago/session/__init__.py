"""Alias module for sago.sessions to ensure backward compatibility and prevent import errors."""

from __future__ import annotations

import sys

import sago.sessions as _sessions_mod
import sago.sessions.manager as _mgr_mod
from sago.sessions.manager import (
    Message,
    Session,
    SessionManager,
    SessionStatus,
    Thread,
    ThreadStatus,
    export_session,
    import_session,
    load_session,
)

manager = _mgr_mod
sys.modules.setdefault("sago.session", _sessions_mod)
sys.modules.setdefault("sago.session.manager", _mgr_mod)

__all__ = [
    "Message",
    "Session",
    "SessionManager",
    "SessionStatus",
    "Thread",
    "ThreadStatus",
    "export_session",
    "import_session",
    "load_session",
    "manager",
]
