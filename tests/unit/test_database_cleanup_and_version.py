"""Tests for database multi-threading cleanup and dynamic versioning."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import sago
from sago.database import (
    _connections,
    _get_connection,
    _pool_lock,
    close_all_connections,
)


def test_sqlite_cross_thread_closing():
    """Verify connections opened in background threads can be closed from main thread."""
    thread_conns = []

    def worker():
        conn = _get_connection()
        conn.execute("SELECT 1").fetchone()
        thread_conns.append(conn)

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert len(thread_conns) == 1
    # Now close all connections from the main thread (simulating atexit / process exit)
    # This must not raise sqlite3.ProgrammingError
    close_all_connections()

    with _pool_lock:
        assert len(_connections) == 0


def test_dynamic_version_consistency():
    """Verify __version__ is dynamic and matches package metadata or fallback."""
    assert isinstance(sago.__version__, str)
    assert len(sago.__version__.split(".")) >= 3

    # Check that TUI command handler uses sago.__version__
    from sago.tui.commands import CommandHandlers

    mock_app = MagicMock()
    mock_app.messages = []
    messages = []
    mock_app._add_system_message = lambda msg: messages.append(msg)

    CommandHandlers._show_version(mock_app)
    assert len(messages) == 1
    assert sago.__version__ in messages[0]
