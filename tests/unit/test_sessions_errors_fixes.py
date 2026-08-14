"""Tests for session status restore and error handler fixes."""

from __future__ import annotations

import json
import logging

from sago.errors.handler import (
    ErrorHandler,
    RecoveryManager,
    RecoveryStrategy,
)
from sago.sessions.manager import (
    Session,
    SessionManager,
    SessionStatus,
    ThreadStatus,
    _restore_session_status,
    _restore_thread_status,
)

# ---------------------------------------------------------------------------
# Session status restore
# ---------------------------------------------------------------------------


def _build_session_with_status(status: SessionStatus) -> tuple[SessionManager, Session]:
    manager = SessionManager()
    session = manager.create_session(title="restore me")
    session.status = status
    thread = manager.create_thread(session.id, "agent", "do work")
    thread.status = ThreadStatus.RUNNING
    thread.started_at = 1234.5
    return manager, session


def test_status_restored_on_import(tmp_path):
    manager, session = _build_session_with_status(SessionStatus.RUNNING)

    exported = manager.export_session(session.id)
    session_file = tmp_path / "session.json"
    session_file.write_text(exported, encoding="utf-8")

    loaded = SessionManager().import_session(session_file.read_text(encoding="utf-8"))
    assert loaded is not None
    assert loaded.status == SessionStatus.RUNNING
    assert loaded.threads[0].status == ThreadStatus.RUNNING
    assert loaded.threads[0].started_at == 1234.5


def test_completed_status_restored_on_import(tmp_path):
    manager, session = _build_session_with_status(SessionStatus.COMPLETED)

    session_file = tmp_path / "session.json"
    session_file.write_text(manager.export_session(session.id), encoding="utf-8")

    loaded = SessionManager().import_session(session_file.read_text(encoding="utf-8"))
    assert loaded is not None
    assert loaded.status == SessionStatus.COMPLETED


def test_legacy_interrupted_status_migrated(tmp_path):
    data = {
        "id": "sess-1",
        "title": "legacy",
        "status": "interrupted",
        "threads": [
            {
                "id": "t-1",
                "session_id": "sess-1",
                "agent_name": "agent",
                "task": "work",
                "status": "interrupted",
            }
        ],
        "messages": [],
    }
    session_file = tmp_path / "legacy.json"
    session_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = SessionManager().import_session(session_file.read_text(encoding="utf-8"))
    assert loaded is not None
    # "interrupted" is migrated to the closest current state.
    assert loaded.status == SessionStatus.PAUSED
    assert loaded.threads[0].status == ThreadStatus.CANCELLED


def test_missing_thread_status_defaults_to_pending(tmp_path):
    data = {
        "id": "sess-2",
        "title": "no-status",
        "status": "idle",
        "threads": [
            {
                "id": "t-2",
                "session_id": "sess-2",
                "agent_name": "agent",
                "task": "work",
            }
        ],
    }
    session_file = tmp_path / "nostatus.json"
    session_file.write_text(json.dumps(data), encoding="utf-8")

    loaded = SessionManager().import_session(session_file.read_text(encoding="utf-8"))
    assert loaded is not None
    assert loaded.threads[0].status == ThreadStatus.PENDING


def test_restore_session_status_helpers():
    assert _restore_session_status({"status": "running"}) == SessionStatus.RUNNING
    assert _restore_session_status({}) == SessionStatus.IDLE
    assert _restore_session_status({"status": "interrupted"}) == SessionStatus.PAUSED
    assert _restore_session_status({"status": "bogus"}) == SessionStatus.IDLE
    assert _restore_thread_status({"status": "running"}) == ThreadStatus.RUNNING
    assert _restore_thread_status({}) == ThreadStatus.PENDING
    assert _restore_thread_status({"status": "interrupted"}) == ThreadStatus.CANCELLED


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------


def test_handle_error_records_and_notifies():
    handler = ErrorHandler()
    captured = []
    handler.on_error = lambda ctx: captured.append(ctx)

    ctx = handler.handle_error("my_tool", ValueError("boom"), attempt=1)

    assert ctx.tool_name == "my_tool"
    assert isinstance(ctx.error, ValueError)
    assert ctx in handler.errors
    assert captured == [ctx]


def test_handle_error_logs(caplog):
    handler = ErrorHandler()
    with caplog.at_level(logging.WARNING, logger="sago.errors.handler"):
        handler.handle_error("my_tool", ValueError("boom"), attempt=1)

    assert any(
        "my_tool" in rec.message and rec.levelno >= logging.WARNING for rec in caplog.records
    )


def test_handle_error_critical_logged_as_error(caplog):
    handler = ErrorHandler()
    with caplog.at_level(logging.DEBUG, logger="sago.errors.handler"):
        handler.handle_error("my_tool", RuntimeError("fatal"), attempt=1)

    assert any(rec.levelno == logging.ERROR for rec in caplog.records)


def test_recovery_retries_transient_then_succeeds():
    manager = RecoveryManager(max_retries=3, retry_delay=0.0, backoff=2.0)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError("temporary")
        return "ok"

    result = manager.execute_with_recovery("tool", flaky)
    assert result.success is True
    assert result.result == "ok"
    assert result.attempts_made == 2
    assert result.strategy_used == RecoveryStrategy.RETRY


def test_recovery_does_not_retry_permanent_error():
    manager = RecoveryManager(max_retries=3, retry_delay=0.0, backoff=2.0)
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise ValueError("permanent")

    result = manager.execute_with_recovery("tool", broken)
    assert result.success is False
    assert calls["n"] == 1  # failed fast, no retries
    assert result.strategy_used == RecoveryStrategy.ABORT
    assert isinstance(result.error, ValueError)


def test_recovery_clean_success_strategy_skip():
    manager = RecoveryManager(max_retries=3, retry_delay=0.0)
    result = manager.execute_with_recovery("tool", lambda: "done")
    assert result.success is True
    assert result.attempts_made == 1
    assert result.strategy_used == RecoveryStrategy.SKIP
