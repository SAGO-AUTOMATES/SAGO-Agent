"""Comprehensive test suite for sago.sessions.manager (Multi-Session and Thread Manager)."""

from __future__ import annotations

import time

from sago.sessions.manager import (
    Message,
    SessionManager,
    SessionStatus,
    Thread,
    ThreadStatus,
    _restore_session_status,
    _restore_thread_status,
    is_summary_intent,
)


class TestSessionManagerUnit:
    """Test full life-cycle, thread execution, branching, and serialization of SessionManager."""

    def test_status_restoration_and_migrations(self) -> None:
        """Verify schema migration fallbacks."""
        assert _restore_session_status({"status": "interrupted"}) == SessionStatus.PAUSED
        assert _restore_session_status({"status": "running"}) == SessionStatus.RUNNING
        assert _restore_session_status({"status": "unknown_value"}) == SessionStatus.IDLE
        assert _restore_session_status({}) == SessionStatus.IDLE

        assert _restore_thread_status({"status": "interrupted"}) == ThreadStatus.CANCELLED
        assert _restore_thread_status({"status": "running"}) == ThreadStatus.RUNNING
        assert _restore_thread_status({"status": "invalid"}) == ThreadStatus.PENDING
        assert _restore_thread_status({}) == ThreadStatus.PENDING

    def test_thread_duration_and_dict(self) -> None:
        th = Thread(
            id="t1",
            session_id="s1",
            agent_name="python-engineer",
            task="Write algorithm",
        )
        assert th.duration() == 0.0
        th.started_at = time.time() - 5.0
        th.completed_at = time.time()
        assert th.duration() >= 4.9

        d = th.to_dict()
        assert d["id"] == "t1"
        assert d["agent_name"] == "python-engineer"
        assert d["status"] == "pending"

    def test_message_creation_and_dict(self) -> None:
        msg = Message(
            id="m1",
            session_id="s1",
            thread_id="t1",
            role="user",
            content="Hello world",
        )
        d = msg.to_dict()
        assert d["id"] == "m1"
        assert d["content"] == "Hello world"

    def test_create_and_manage_session(self) -> None:
        mgr = SessionManager()
        sess = mgr.create_session("Build REST API")
        assert sess.id in mgr.sessions
        assert sess.title == "Build REST API"
        assert sess.status == SessionStatus.IDLE

        # Add message
        msg = sess.add_message("user", "Design users table", agent_name="architect")
        assert msg in sess.messages
        assert len(sess.messages) == 1

        # Add threads
        t1 = Thread(
            id="th1",
            session_id=sess.id,
            agent_name="architect",
            task="Task 1",
            status=ThreadStatus.RUNNING,
        )
        t2 = Thread(
            id="th2",
            session_id=sess.id,
            agent_name="python-engineer",
            task="Task 2",
            status=ThreadStatus.COMPLETED,
        )
        sess.threads.extend([t1, t2])

        assert len(sess.active_threads()) == 1
        assert len(sess.completed_threads()) == 1

        # Dict representation
        d = sess.to_dict()
        assert d["id"] == sess.id
        assert d["message_count"] == 1
        assert len(d["threads"]) == 2

    def test_session_manager_methods(self) -> None:
        mgr = SessionManager()
        s1 = mgr.create_session("S1")
        mgr.create_session("S2")  # create second session to verify list

        retrieved = mgr.get_session(s1.id)
        assert retrieved is s1

        all_sess = mgr.list_sessions()
        assert len(all_sess) >= 2

        # Delete session
        mgr.delete_session(s1.id)
        assert mgr.get_session(s1.id) is None

    def test_is_summary_intent(self) -> None:
        assert is_summary_intent("what was the summary?") is True
        assert is_summary_intent("so what was the sumamry?") is True
        assert is_summary_intent("what did you do") is True
        assert is_summary_intent("summarize README.md") is False
        assert is_summary_intent("") is False
